#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 AgentScope tracing — ReActAgent + KimiHTTPChatModel（对齐 game test_kimi）"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_backend = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend))

env_path = _backend / ".env"
load_dotenv(env_path)

print("=" * 50)
print("Testing AgentScope Tracing with ReActAgent + KimiHTTPChatModel")
print("=" * 50)

import agentscope

studio_url = os.environ.get("AGENTSCOPE_STUDIO_URL")
print(f"\n1. AgentScope Studio URL: {studio_url}")

if studio_url:
    agentscope.init(
        studio_url=studio_url,
        project="doc_revewer",
        name="test_run",
    )
    agentscope._config.trace_enabled = True

print(f"   trace_enabled: {agentscope._config.trace_enabled}")
print(f"   run_id: {agentscope._config.run_id}")
print(f"   project: {agentscope._config.project}")

from agents.agentscope_agent import create_document_review_react_agent, msg_to_text
from agentscope.message import Msg

print("\n2. Creating ReActAgent...")


async def test_llm():
    agent = create_document_review_react_agent(
        api_key=os.environ.get("KIMI_API_KEY"),
        sys_prompt="你是一个有帮助的助手",
        name="TraceTest",
        max_iters=3,
    )
    print("\n3. Calling agent (trace_llm + trace_reply)...")
    reply = await agent(Msg("user", "你好，请用一句话回复", "user"))
    response = msg_to_text(reply)
    print(f"   Response: {response[:100]}...")
    print("\n✅ LLM call completed!")
    print("   请在 AgentScope Studio 的 Run TRACE 标签页查看 trace 数据")


asyncio.run(test_llm())
