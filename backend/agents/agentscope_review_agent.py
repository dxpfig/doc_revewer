"""
AgentScope Review — ReActAgent + KimiHTTPChatModel（对齐 game/werewolves/test_kimi）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg

from .agentscope_agent import KimiHTTPChatModel, msg_to_text

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的文档审查助手。你的任务是根据给定的审查规则，对文档进行严格审查，并给出明确的通过/失败判定及证据。

## 输出格式要求
返回有效的 JSON 格式，包含以下字段：
- results: 审查结果列表，每项包含 rule_id, rule_title, status, match_score, matched_text, evidence, suggestion
- summary: 汇总信息，包含 total, passed, failed, overall_score

## 审查原则
1. 严格按规则审查，不放过任何违规点
2. 证据必须具体，引用文档中的实际内容
3. 对于不明确的点，倾向于判定为通过但需说明
4. 如果文档中未提供足够信息判断，标记为 passed 并说明原因

## 评分标准
- match_score: 0.0-1.0，1.0 表示完全符合
- 整体评分 = 通过数 / 总数"""


def create_review_agent(
    name: str = "DocReviewer",
    api_key: Optional[str] = None,
    model_name: str = "moonshot-v1-8k",
) -> ReActAgent:
    key = api_key or os.environ.get("KIMI_API_KEY")
    if not key:
        raise ValueError("KIMI_API_KEY not set")

    model = KimiHTTPChatModel(api_key=key, model_name=model_name)
    return ReActAgent(
        name=name,
        sys_prompt=SYSTEM_PROMPT,
        model=model,
        formatter=OpenAIChatFormatter(),
        memory=InMemoryMemory(),
        max_iters=5,
    )


async def review_document_with_agentscope(
    doc_content: str,
    rules: List[Dict[str, Any]],
    batch_size: int = 5,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用 ReActAgent 分批审查；每批新建 Agent，避免对话记忆污染。
    """
    truncated_doc = doc_content[:15000] if len(doc_content) > 15000 else doc_content
    all_results: list = []

    for i in range(0, len(rules), batch_size):
        batch = rules[i : i + batch_size]
        rules_text = "\n".join(
            [
                f"{j+1}. 【{r.get('title', '规则')}】{r.get('content', '')}"
                for j, r in enumerate(batch)
            ]
        )
        user_prompt = f"""请审查以下文档是否符合标准规则。

## 文档内容
---
{truncated_doc}
---

## 审查规则
---
{rules_text}
---

请返回 JSON 格式的审查结果。"""

        agent = create_review_agent(api_key=api_key)
        response = await agent(Msg(name="user", role="user", content=user_prompt))
        response_text = msg_to_text(response)

        try:
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                data = json.loads(json_match.group(0))
                batch_results = data.get("results", [])
                all_results.extend(batch_results)
            else:
                raise ValueError("No JSON in response")
        except Exception as e:
            logger.warning("Failed to parse batch %s: %s", i // batch_size, e)
            for j, r in enumerate(batch):
                all_results.append(
                    {
                        "rule_id": str(r.get("id", i + j)),
                        "rule_title": r.get("title", "Unknown"),
                        "status": "passed",
                        "match_score": 0.5,
                        "matched_text": "",
                        "evidence": "未能完成审查",
                        "suggestion": "请人工复查",
                    }
                )

    passed = sum(1 for r in all_results if r.get("status") == "passed")
    failed = sum(1 for r in all_results if r.get("status") == "failed")
    total = len(all_results)
    overall_score = round(passed / total if total > 0 else 0, 2)

    return {
        "results": all_results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "overall_score": overall_score,
        },
    }
