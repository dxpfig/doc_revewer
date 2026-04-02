"""
文档审查 Agent — 对齐 resources/examples/game/werewolves/test_kimi.py：
使用 AgentScope 内置 ReActAgent + ChatModelBase（Moonshot HTTP），获得 trace_llm / trace_reply。
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal, Optional, Type

import httpx
from pydantic import BaseModel

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg, TextBlock, ToolUseBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.model._model_usage import ChatUsage
from agentscope.tracing import trace_llm

logger = logging.getLogger(__name__)


def _msg_content_to_plain_text(content: str | list) -> str:
    """从 Msg.content 提取纯文本（供解析 JSON）。"""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def msg_to_text(msg: Msg) -> str:
    """ReActAgent 返回的 Msg → 字符串。"""
    return _msg_content_to_plain_text(msg.content)


def _normalize_messages_for_kimi(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 formatter 产出的 message 转为 Moonshot/OpenAI chat 可接受的格式。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(str(part.get("text", "")))
                elif isinstance(part, str):
                    texts.append(part)
            content = "\n".join(texts) if texts else ""
        out.append({"role": role, "content": content})
    return out


class KimiHTTPChatModel(ChatModelBase):
    """
    Moonshot（Kimi）OpenAI 兼容 Chat Completions，继承 ChatModelBase 以启用 @trace_llm。
    参考 resources/examples/game/werewolves/test_kimi.py 的调用方式。
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "moonshot-v1-8k",
        base_url: str = "https://api.moonshot.cn/v1",
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, stream=False)
        self.api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        if kwargs:
            logger.debug("KimiHTTPChatModel ignoring kwargs: %s", list(kwargs.keys()))

    @trace_llm
    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        structured_model: Type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        if structured_model is not None:
            logger.warning(
                "KimiHTTPChatModel 未实现 structured_model，将忽略并以纯文本调用"
            )

        msgs = _normalize_messages_for_kimi(messages)
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": msgs,
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 4096)),
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None and tools:
            payload["tool_choice"] = tool_choice

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Kimi API error: {response.status_code} - {response.text}"
                )
            data = response.json()

        choice = data["choices"][0]
        message = choice.get("message") or {}
        raw_content = message.get("content") or ""
        tool_calls = message.get("tool_calls")

        blocks: list[TextBlock | ToolUseBlock] = []
        if raw_content:
            blocks.append(TextBlock(type="text", text=raw_content))

        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                args = fn.get("arguments", "{}")
                try:
                    input_obj: dict[str, object] = json.loads(args) if isinstance(args, str) else {}
                except json.JSONDecodeError:
                    input_obj = {"raw": args}
                blocks.append(
                    ToolUseBlock(
                        type="tool_use",
                        id=tc.get("id", ""),
                        name=name,
                        input=input_obj,
                    )
                )

        if not blocks:
            blocks.append(TextBlock(type="text", text=""))

        usage_raw = data.get("usage") or {}
        usage = ChatUsage(
            input_tokens=int(usage_raw.get("prompt_tokens", 0)),
            output_tokens=int(usage_raw.get("completion_tokens", 0)),
            time=0.0,
        )

        return ChatResponse(
            content=blocks,
            id=str(data.get("id", f"kimi_{int(time.time())}")),
            usage=usage,
            metadata={},
        )


def create_document_review_react_agent(
    *,
    api_key: Optional[str] = None,
    sys_prompt: str,
    name: str = "DocReviewer",
    model_name: str = "moonshot-v1-8k",
    base_url: str = "https://api.moonshot.cn/v1",
    max_iters: int = 5,
) -> ReActAgent:
    """
    创建用于「单轮/少轮 JSON 审查」的 ReActAgent（空 toolkit，行为接近 test_kimi.py）。
    每批规则建议新建实例，避免 memory 串话。
    """
    key = api_key or os.environ.get("KIMI_API_KEY")
    if not key:
        raise ValueError("KIMI_API_KEY not set")

    model = KimiHTTPChatModel(
        api_key=key,
        model_name=model_name,
        base_url=base_url,
    )
    return ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=model,
        formatter=OpenAIChatFormatter(),
        memory=InMemoryMemory(),
        max_iters=max_iters,
    )


# 兼容旧名称（逐步废弃）
def create_doc_reviewer_agent(
    name: str = "DocReviewer",
    sys_prompt: str = "你是一个专业的文档审查助手。",
    api_key: Optional[str] = None,
    model: str = "moonshot-v1-8k",
    **kwargs: Any,
) -> ReActAgent:
    """兼容旧 API：返回 ReActAgent。"""
    return create_document_review_react_agent(
        api_key=api_key,
        sys_prompt=sys_prompt,
        name=name,
        model_name=model,
        **kwargs,
    )


# 旧 KimiLLM / DocReviewerAgent 已移除；请使用 KimiHTTPChatModel + ReActAgent

__all__ = [
    "KimiHTTPChatModel",
    "create_document_review_react_agent",
    "create_doc_reviewer_agent",
    "msg_to_text",
]
