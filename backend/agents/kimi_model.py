# -*- coding: utf-8 -*-
"""Kimi 模型工厂：与 game/werewolves/test_kimi 一致，使用 KimiHTTPChatModel（ChatModelBase）。"""
from __future__ import annotations

import os
from typing import Any, Optional

from .agentscope_agent import KimiHTTPChatModel


def create_kimi_model(
    api_key: Optional[str] = None,
    model_name: str = "moonshot-v1-8k",
    **kwargs: Any,
) -> KimiHTTPChatModel:
    """供 ReActAgent 等使用的 Kimi Chat 模型（带 trace_llm）。"""
    key = api_key or os.environ.get("KIMI_API_KEY")
    if not key:
        raise ValueError("KIMI_API_KEY not set")
    return KimiHTTPChatModel(api_key=key, model_name=model_name, **kwargs)
