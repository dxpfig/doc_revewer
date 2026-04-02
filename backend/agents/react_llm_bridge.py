# -*- coding: utf-8 -*-
"""
通过 AgentScope ReActAgent + ChatModelBase 执行「系统提示 + 用户内容」单轮对话。
供规则抽取、分类、文档审查等场景统一走 trace_llm / trace_reply。
在已有 asyncio 事件循环的上下文中，通过独立线程 + asyncio.run 避免嵌套循环；
子线程内用 copy_context 继承 trace_enabled / run_id 等，避免 trace_llm 被跳过。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
from dataclasses import dataclass
from typing import Any, Optional

from agentscope.agent import ReActAgent
from agentscope.formatter import AnthropicChatFormatter, OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import AnthropicChatModel, ChatModelBase, OpenAIChatModel

from .agentscope_agent import KimiHTTPChatModel, msg_to_text

logger = logging.getLogger(__name__)


class _BoundKimiHTTPChatModel(KimiHTTPChatModel):
    """ReActAgent 调用 model() 时不带 temperature/max_tokens，在此注入默认值。"""

    def __init__(
        self,
        *,
        bind_temperature: float,
        bind_max_tokens: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._bind_temperature = bind_temperature
        self._bind_max_tokens = bind_max_tokens

    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        structured_model: Any = None,
        **kwargs: Any,
    ) -> Any:
        kwargs.setdefault("temperature", self._bind_temperature)
        kwargs.setdefault("max_tokens", self._bind_max_tokens)
        return await super().__call__(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            structured_model=structured_model,
            **kwargs,
        )


_DEFAULT_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com/v1",
    "minimax": "https://api.minimax.chat/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "local": "http://localhost:8000/v1",
}


def create_chat_model_for_provider(
    provider_type: str,
    base_url: Optional[str],
    api_key: str,
    model: str,
    *,
    timeout: float = 120.0,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> ChatModelBase:
    """按 provider 构造 AgentScope ChatModelBase（均带 trace_llm）。"""
    pt = (provider_type or "openai").lower()
    bu = (base_url or _DEFAULT_URLS.get(pt, _DEFAULT_URLS["openai"])).rstrip("/")

    if pt == "moonshot":
        return _BoundKimiHTTPChatModel(
            bind_temperature=temperature,
            bind_max_tokens=max_tokens,
            api_key=api_key,
            model_name=model,
            base_url=bu,
            timeout=timeout,
        )
    if pt == "anthropic":
        return AnthropicChatModel(
            model_name=model,
            api_key=api_key,
            stream=False,
            max_tokens=max_tokens,
            generate_kwargs={"temperature": temperature},
        )
    # OpenAI 兼容：openai / deepseek / minimax / local
    return OpenAIChatModel(
        model_name=model,
        api_key=api_key,
        stream=False,
        client_kwargs={"base_url": bu},
        generate_kwargs={
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )


def formatter_for_model(model: ChatModelBase) -> Any:
    if isinstance(model, AnthropicChatModel):
        return AnthropicChatFormatter()
    return OpenAIChatFormatter()


async def react_llm_complete(
    system: str,
    user: str,
    model: ChatModelBase,
    *,
    agent_name: str = "LLMWorker",
    max_iters: int = 5,
) -> str:
    """单次用户消息，sys_prompt=system，返回助手文本。"""
    agent = ReActAgent(
        name=agent_name,
        sys_prompt=system,
        model=model,
        formatter=formatter_for_model(model),
        memory=InMemoryMemory(),
        max_iters=max_iters,
    )
    reply = await agent(Msg("user", user, "user"))
    return msg_to_text(reply)


def run_react_llm_isolated(
    system: str,
    user: str,
    model: ChatModelBase,
    *,
    agent_name: str = "LLMWorker",
    max_iters: int = 5,
) -> str:
    """
    在任意线程/协程环境下执行 react_llm_complete。
    若当前线程已有运行中的事件循环，则放到新线程里 asyncio.run。
    新线程会丢失默认 ContextVar，须复制调用方上下文，否则 agentscope trace_enabled 为 False。
    """
    async def _run() -> str:
        return await react_llm_complete(
            system,
            user,
            model,
            agent_name=agent_name,
            max_iters=max_iters,
        )

    def _thread_entry() -> str:
        return asyncio.run(_run())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())

    ctx = contextvars.copy_context()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(ctx.run, _thread_entry)
        return fut.result(timeout=900)


@dataclass
class ReactLLMBackend:
    """
    替代原 BaseAgent：保存 Provider 凭证，通过 ReActAgent 调用模型。
    """

    provider_type: str
    base_url: Optional[str]
    api_key: str
    model: str
    timeout: float = 120.0
    temperature: float = 0.7
    max_tokens: int = 4096

    def call_llm(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        t = temperature if temperature is not None else self.temperature
        mt = max_tokens if max_tokens is not None else self.max_tokens
        model = create_chat_model_for_provider(
            self.provider_type,
            self.base_url,
            self.api_key,
            self.model,
            timeout=self.timeout,
            temperature=float(t),
            max_tokens=int(mt),
        )
        return run_react_llm_isolated(
            system,
            user,
            model,
            agent_name=f"react_{self.provider_type}",
            max_iters=5,
        )


def create_react_backend(
    provider_type: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs: Any,
) -> ReactLLMBackend:
    """与原 BaseAgent 构造函数参数兼容。"""
    pt = provider_type
    bu = base_url or _DEFAULT_URLS.get(pt, _DEFAULT_URLS["openai"])
    if not api_key:
        raise ValueError("api_key is required")
    default_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "deepseek": "deepseek-chat",
        "minimax": "abab6.5s-chat",
        "moonshot": "moonshot-v1-8k",
        "local": "gpt-3.5-turbo",
    }
    m = model or default_models.get(pt, "gpt-4o-mini")
    return ReactLLMBackend(
        provider_type=pt,
        base_url=bu,
        api_key=api_key,
        model=m,
        timeout=float(kwargs.get("timeout", 120)),
        temperature=float(kwargs.get("temperature", 0.7)),
        max_tokens=int(kwargs.get("max_tokens", 4096)),
    )
