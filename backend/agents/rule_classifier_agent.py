"""
Rule Classifier Agent - 使用 LLM 分析标准文本，分类规则
将规则按组分类，返回结构化的规则列表
"""
import json
import re
import logging
from typing import List, Dict, Any, Optional

from .react_llm_bridge import ReactLLMBackend, create_react_backend

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的文档审查标准分析助手。你的任务是从标准文档中提取审查规则，并将规则按类型分组。

## 输出格式要求
你必须返回有效的 JSON 格式，结构如下：
{
    "rule_groups": [
        {
            "group_name": "组名",
            "description": "组描述",
            "rules": [
                {
                    "title": "规则标题",
                    "content": "规则总结（用于后续自动审查的判定依据）",
                    "source_page": 页码,
                    "source_excerpt": "原文摘录"
                }
            ]
        }
    ],
    "summary": "整体摘要"
}

## 分类指导
将规则按以下维度分类：
1. 内容完整性 - 文档必须包含的要素
2. 格式规范 - 文档格式要求
3. 逻辑一致性 - 内部逻辑要求
4. 表述准确性 - 用词表述要求
5. 法规符合性 - 法规政策要求
6. 其他 - 不属于以上类别的规则

## 注意事项
- 只提取可以被审查的规则（必须有明确的检查点）
- 对于无法提取具体规则的页面，标注"无可审查规则"
- source_page 为数字，如无可提取信息则设为 null
- content 必须是“总结后的可执行规则”，不要直接复制原文，避免冗长
- content 建议 30-80 字，表达明确、可检查、单一要求
- 确保 JSON 格式正确，不要有语法错误"""


USER_PROMPT_TEMPLATE = """请分析以下标准文档，提取审查规则并分类。

标准文档内容：
---
{content}
---

请返回 JSON 格式的分析结果。"""


class RuleClassifierAgent:
    """Agent for classifying rules from standard documents using LLM (ReActAgent + ChatModelBase)"""

    def __init__(self, backend: ReactLLMBackend, **kwargs):
        self._backend = backend
        self.system_prompt = SYSTEM_PROMPT

    def run(self, content: str) -> Dict[str, Any]:
        """
        分析标准文本，提取并分类规则

        Args:
            content: 标准文档的文本内容

        Returns:
            结构化的规则分类结果:
            {
                "rule_groups": [...],
                "summary": "..."
            }
        """
        # 限制内容长度，避免超出 LLM 上下文限制
        truncated_content = self._truncate_content(content)

        user_prompt = USER_PROMPT_TEMPLATE.format(content=truncated_content)

        try:
            response = self._backend.call_llm(
                system=self.system_prompt,
                user=user_prompt,
                temperature=0.3,  # 较低温度，更一致的输出
                max_tokens=8192
            )

            # 解析 JSON 响应
            result = self._parse_response(response)
            result = self._normalize_result(result)
            return result

        except Exception as e:
            logger.error(f"Rule classification failed: {str(e)}")
            return {
                "rule_groups": [],
                "error": str(e),
                "summary": "规则分类失败"
            }

    def _truncate_content(self, content: str, max_length: int = 15000) -> str:
        """截断内容，避免超出 LLM 上下文限制"""
        if len(content) <= max_length:
            return content

        # 保留开头和结尾，中间部分截断
        head = content[:max_length // 2]
        tail = content[-max_length // 2:]
        return f"{head}\n\n... [内容截断] ...\n\n{tail}"

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应，提取 JSON"""
        try:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                # 直接解析整个响应
                return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {str(e)}")
            logger.debug(f"Raw response: {response}")
            return {
                "rule_groups": [],
                "error": "JSON 解析失败",
                "raw_response": response[:500]
            }

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化模型输出，确保 content 为可执行总结，而非原文照抄。
        """
        groups = result.get("rule_groups", [])
        if not isinstance(groups, list):
            result["rule_groups"] = []
            return result

        for group in groups:
            rules = group.get("rules", [])
            if not isinstance(rules, list):
                group["rules"] = []
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                title = str(rule.get("title", "")).strip()
                content = str(rule.get("content", "")).strip()
                excerpt = str(rule.get("source_excerpt", "")).strip()

                # 缺失时用标题兜底
                if not content:
                    rule["content"] = title
                    continue

                # 过长或疑似照抄原文时做二次总结
                if len(content) > 120 or (excerpt and content == excerpt):
                    summarized = self._summarize_rule_content(title, content, excerpt)
                    if summarized:
                        rule["content"] = summarized
                    else:
                        # 最差兜底：截断到可读范围
                        rule["content"] = content[:120]

        return result

    def _summarize_rule_content(self, title: str, content: str, source_excerpt: str) -> str:
        """
        将单条规则内容压缩为“可执行检查句”。
        """
        prompt = f"""请将下面规则整理为一条可执行检查句，用于自动审查判定。

标题：{title}
原始规则：{content}
原文摘录：{source_excerpt}

要求：
1) 输出 30-80 字中文；
2) 必须包含明确检查点（例如“应包含”“不得缺少”“必须满足”）；
3) 不要照抄原文长段；
4) 仅输出一句话，不要解释。"""
        try:
            text = self._backend.call_llm(
                system="你是文档规则制定专家，负责输出可执行文档审查规则。",
                user=prompt,
                temperature=0.1,
                max_tokens=200,
            ).strip()
            # 清理可能的包裹
            text = text.replace("```", "").strip()
            return text[:120]
        except Exception as e:
            logger.warning(f"Rule summarize failed: {str(e)}")
            return ""

    def classify_simple(self, text: str) -> str:
        """
        简单分类：将单条规则文本分类到对应组

        Args:
            text: 规则文本

        Returns:
            分类结果
        """
        prompt = f"""请将以下规则分类到对应的组。

规则内容：{text}

可选组别：
- 内容完整性
- 格式规范
- 逻辑一致性
- 表述准确性
- 法规符合性
- 其他

直接返回组名，不要包含其他内容。"""

        try:
            return self._backend.call_llm(
                system="你是一个规则分类助手。",
                user=prompt,
                temperature=0.1,
                max_tokens=100
            ).strip()
        except Exception as e:
            logger.warning(f"Simple classification failed: {str(e)}")
            return "其他"


def create_rule_classifier(
    provider_type: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> RuleClassifierAgent:
    """创建 RuleClassifierAgent 的便捷函数"""
    backend = create_react_backend(
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        **kwargs
    )
    return RuleClassifierAgent(backend)