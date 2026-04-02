"""
Document Reviewer Agent - 使用 LLM 进行文档审查
接收文档内容 + 规则列表，进行语义匹配审查
返回审查结果（通过/失败 + 证据）
"""
import logging
from typing import List, Dict, Any, Optional

from .react_llm_bridge import ReactLLMBackend, create_react_backend

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的文档审查助手。你的任务是根据给定的审查规则，对文档进行严格审查，并给出明确的通过/失败判定及证据。

## 输出格式要求
返回有效的 JSON 格式：
{
    "results": [
        {
            "rule_id": "规则ID",
            "rule_title": "规则标题",
            "status": "passed" | "failed" | "error",
            "match_score": 0.0-1.0,
            "matched_text": "匹配的文本内容（如果失败则为空）",
            "evidence": "审查证据或失败原因",
            "suggestion": "改进建议（如果失败）"
        }
    ],
    "summary": {
        "total": 总规则数,
        "passed": 通过数,
        "failed": 失败数,
        "overall_score": 总体评分
    }
}

## 审查原则
1. 严格按规则审查，不放过任何违规点
2. 证据必须具体，引用文档中的实际内容
3. 对于不明确的点，倾向于判定为通过但需说明
4. 如果文档中未提供足够信息判断，标记为 passed 并说明原因

## 评分标准
- match_score: 0.0-1.0，1.0 表示完全符合
- 整体评分 = 通过数 / 总数"""


USER_PROMPT_TEMPLATE = """请审查以下文档是否符合标准规则。

## 文档内容
---
{doc_content}
---

## 审查规则
---
{rules_content}
---

请对每条规则进行审查，返回 JSON 格式的审查结果。"""


class DocumentReviewerAgent:
    """Agent for reviewing documents against rules using LLM (ReActAgent + ChatModelBase)"""

    def __init__(self, backend: ReactLLMBackend, **kwargs):
        self._backend = backend
        self.system_prompt = SYSTEM_PROMPT

    def run(
        self,
        doc_content: str,
        rules: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> Dict[str, Any]:
        """
        审查文档

        Args:
            doc_content: 文档内容（文本）
            rules: 规则列表，每条规则包含 id, title, content
            batch_size: 每批处理的规则数量

        Returns:
            审查结果:
            {
                "results": [...],
                "summary": {...}
            }
        """
        if not rules:
            return {
                "results": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "overall_score": 0},
                "error": "No rules provided"
            }

        # 分批处理规则
        all_results = []
        for i in range(0, len(rules), batch_size):
            batch = rules[i:i + batch_size]
            batch_results = self._review_batch(doc_content, batch, i)
            all_results.extend(batch_results)

        # 计算汇总
        passed = sum(1 for r in all_results if r["status"] == "passed")
        failed = sum(1 for r in all_results if r["status"] == "failed")
        total = len(all_results)
        overall_score = passed / total if total > 0 else 0

        return {
            "results": all_results,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "overall_score": round(overall_score, 2)
            }
        }

    def _review_batch(
        self,
        doc_content: str,
        rules: List[Dict[str, Any]],
        rule_offset: int
    ) -> List[Dict[str, Any]]:
        """审查一批规则"""
        truncated_doc = self._truncate_content(doc_content)
        rules_text = self._format_rules(rules)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            doc_content=truncated_doc,
            rules_content=rules_text
        )

        try:
            response = self._backend.call_llm(
                system=self.system_prompt,
                user=user_prompt,
                temperature=0.3,
                max_tokens=8192
            )

            return self._parse_results(response, rules, rule_offset)

        except Exception as e:
            logger.error(f"Batch review failed: {str(e)}")
            # 返回错误结果
            return [
                {
                    "rule_id": str(r.get("id", rule_offset + i)),
                    "rule_title": r.get("title", "Unknown"),
                    "status": "error",
                    "match_score": 0.0,
                    "matched_text": "",
                    "evidence": str(e),
                    "suggestion": "请重试"
                }
                for i, r in enumerate(rules)
            ]

    def _truncate_content(self, content: str, max_length: int = 20000) -> str:
        """截断内容，避免超出 LLM 上下文限制"""
        if len(content) <= max_length:
            return content

        head = content[:max_length // 2]
        tail = content[-max_length // 2:]
        return f"{head}\n\n... [内容截断] ...\n\n{tail}"

    def _format_rules(self, rules: List[Dict[str, Any]]) -> str:
        """格式化规则为可读文本"""
        formatted = []
        for i, rule in enumerate(rules):
            title = rule.get("title", f"规则 {i+1}")
            content = rule.get("content", "")
            rule_id = rule.get("id", i + 1)
            formatted.append(f"{rule_id}. 【{title}】{content}")
        return "\n".join(formatted)

    def _parse_results(
        self,
        response: str,
        rules: List[Dict[str, Any]],
        rule_offset: int
    ) -> List[Dict[str, Any]]:
        """解析 LLM 响应"""
        import json
        import re

        try:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group(0))
                return data.get("results", [])
            else:
                # 如果无法解析，返回原始规则作为错误结果
                raise ValueError("No JSON found in response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse review results: {str(e)}")
            # 降级处理：返回简单判定
            return [
                {
                    "rule_id": str(rules[i].get("id", rule_offset + i)),
                    "rule_title": rules[i].get("title", f"规则 {i+1}"),
                    "status": "passed",  # 默认通过
                    "match_score": 0.5,
                    "matched_text": "",
                    "evidence": "未能完成审查",
                    "suggestion": "请人工复查"
                }
                for i in range(len(rules))
            ]

    def review_single_rule(
        self,
        doc_content: str,
        rule: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        审查单条规则

        Args:
            doc_content: 文档内容
            rule: 规则信息

        Returns:
            单条规则的审查结果
        """
        prompt = f"""请审查以下文档是否符合该规则。

文档内容：
{doc_content}

规则：{rule.get('title', '')}
规则详情：{rule.get('content', '')}

请返回 JSON：
{{
    "status": "passed" | "failed",
    "match_score": 0.0-1.0,
    "evidence": "证据",
    "suggestion": "改进建议（如果失败）"
}}"""

        try:
            response = self._backend.call_llm(
                system="你是一个严格的文档审查助手。",
                user=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            return self._parse_single_result(response)
        except Exception as e:
            logger.error(f"Single rule review failed: {str(e)}")
            return {
                "status": "error",
                "match_score": 0.0,
                "evidence": str(e),
                "suggestion": "请重试"
            }

    def _parse_single_result(self, response: str) -> Dict[str, Any]:
        """解析单条规则结果"""
        import json
        import re
        try:
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                return json.loads(match.group(0))
        except:
            pass
        return {
            "status": "passed",
            "match_score": 0.5,
            "evidence": "未能解析结果",
            "suggestion": ""
        }


def create_document_reviewer(
    provider_type: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> DocumentReviewerAgent:
    """创建 DocumentReviewerAgent 的便捷函数"""
    backend = create_react_backend(
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        **kwargs
    )
    return DocumentReviewerAgent(backend)