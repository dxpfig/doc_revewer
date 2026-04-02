"""
Rule Extractor Agent - 规则提取 Agent
从 OCR 文本或标准文档中提取结构化规则条目
"""
import json
import logging
from typing import List, Dict, Any, Optional

from .react_llm_bridge import ReactLLMBackend, create_react_backend

logger = logging.getLogger(__name__)

# 规则提取的系统提示词
RULE_EXTRACTOR_SYSTEM_PROMPT = """你是一个专业的文档规则提取专家。从GJB标准的正文中提取可以作为规则条目录入数据库的结构化数据。

## 提取要求
1. 每条规则应该包含以下字段：
   - title: 规则标题（简洁明确，50字以内）
   - content: 规则详细内容（完整保留原文的要点）
   - rule_group: 规则所属分组（根据内容归类，如"接口设计"、"数据元素"、"通信方法"等）

2. 提取规则：
   - 只提取具有明确要求的条款（包含"应"、"必须"、"应该"等指令性词汇的内容）
   - 保持原文的层次结构（a) b) c) 或 1) 2) 3) 格式）
   - 如果一个条款下有多个子项，可以拆分为多条规则
   - 每条规则要完整表达一个独立的要求

3. 输出格式：
   - 输出JSON数组，每个元素是一个规则对象
   - 直接输出JSON，不要代码块包裹
   - 不要添加任何解释或评论

## 示例输出
[
  {"title": "接口唯一标识符要求", "content": "本条（从4.3.2开始）应通过唯一标识符来标识接口，应简要地标识接口实体", "rule_group": "接口设计"},
  {"title": "接口实体特性描述", "content": "根据需要可分条描述单方或双方接口实体的特性", "rule_group": "接口设计"}
]"""

RULE_EXTRACTOR_USER_PROMPT_TEMPLATE = """请从以下第{page_num}页内容中提取规则条目：

{text}"""


class RuleExtractorAgent:
    """Agent for extracting structured rules from document text using LLM (ReActAgent + ChatModelBase)"""

    def __init__(self, backend: ReactLLMBackend, **kwargs):
        self._backend = backend
        self.system_prompt = RULE_EXTRACTOR_SYSTEM_PROMPT

    def run(
        self,
        text: str,
        page_num: Optional[int] = None,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取结构化规则

        Args:
            text: 文档文本内容
            page_num: 页码（可选，用于标记规则来源）
            max_retries: 最大重试次数

        Returns:
            规则列表，每个元素包含 title, content, rule_group
        """
        # 跳过 markdown 标记行
        clean_text = text
        if text.strip().startswith('markdown'):
            clean_text = text.replace('markdown\n', '', 1)

        user_prompt = RULE_EXTRACTOR_USER_PROMPT_TEMPLATE.format(
            page_num=page_num or 0,
            text=clean_text
        )

        # 添加重试机制
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self._backend.call_llm(
                    system=self.system_prompt,
                    user=user_prompt,
                    temperature=0.2,  # 较低温度，更稳定的输出
                    max_tokens=4096
                )

                # 解析 JSON 响应
                rules = self._parse_response(response)

                # 添加页码信息
                if page_num:
                    for rule in rules:
                        rule['source_page'] = page_num

                return rules

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Rule extraction attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    import time
                    time.sleep(wait_time)

        logger.error(f"Rule extraction failed after {max_retries} attempts: {last_error}")
        return []

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """解析 LLM 响应，提取规则列表"""
        try:
            # 清理输出
            content = response.strip()
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # 尝试解析 JSON
            rules = json.loads(content)
            return rules if isinstance(rules, list) else []

        except json.JSONDecodeError as e:
            # 尝试提取 JSON 数组
            try:
                start = content.find('[')
                end = content.rfind(']') + 1
                if start >= 0 and end > start:
                    rules = json.loads(content[start:end])
                    return rules if isinstance(rules, list) else []
            except:
                pass

            logger.error(f"Failed to parse rules JSON: {str(e)}")
            return []

    def extract_from_files(
        self,
        file_paths: List[str],
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        从多个文件提取规则

        Args:
            file_paths: OCR 文件路径列表
            max_retries: 最大重试次数

        Returns:
            所有文件的规则合并列表
        """
        all_rules = []

        for file_path in file_paths:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()

                # 从文件名提取页码
                page_num = self._extract_page_num(file_path)

                rules = self.run(text, page_num, max_retries)
                all_rules.extend(rules)

                logger.info(f"Extracted {len(rules)} rules from {file_path}")

            except Exception as e:
                logger.error(f"Failed to process file {file_path}: {e}")

        return all_rules

    def _extract_page_num(self, file_path: str) -> Optional[int]:
        """从文件名提取页码"""
        import os
        filename = os.path.basename(file_path)

        # 尝试从 page_X_ocr.txt 格式提取
        parts = filename.split('_')
        for i, part in enumerate(parts):
            if part == 'page' and i + 1 < len(parts):
                try:
                    return int(parts[i + 1].split('.')[0])
                except ValueError:
                    pass

        return None


def create_rule_extractor(
    provider_type: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> RuleExtractorAgent:
    """创建 RuleExtractorAgent 的便捷函数"""
    backend = create_react_backend(
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        **kwargs
    )
    return RuleExtractorAgent(backend)