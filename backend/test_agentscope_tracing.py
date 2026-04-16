#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 AgentScope tracing"""
import asyncio
import os
from pathlib import Path

# 加载 .env
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

print("=" * 50)
print("Testing AgentScope Tracing")
print("=" * 50)

# 1. 初始化 AgentScope
import agentscope
studio_url = os.environ.get("AGENTSCOPE_STUDIO_URL")
print(f"\n1. AgentScope Studio URL: {studio_url}")

agentscope.init(
    studio_url=studio_url,
    project="doc_revewer",
    name="test_run"
)

print(f"   trace_enabled: {agentscope._config.trace_enabled}")
print(f"   run_id: {agentscope._config.run_id}")
print(f"   project: {agentscope._config.project}")

# 2. 创建 Kimi 模型
from agents.kimi_model import create_kimi_model
print("\n2. Creating Kimi model...")

model = create_kimi_model()
print(f"   Model created: {model}")

# 3. 创建 ReActAgent
from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from agentscope.formatter import OpenAIChatFormatter

print("\n3. Creating ReActAgent...")

agent = ReActAgent(
    name="TestAgent",
    sys_prompt="你是一个有帮助的助手。请用一句话回复。",
    model=model,
    formatter=OpenAIChatFormatter(),
    memory=InMemoryMemory()
)

print(f"   Agent created: {agent.name}")

# 4. 调用 Agent
from agentscope.message import Msg

async def test_agent():
    print("\n4. Calling Agent (with tracing)...")

    msg = Msg(name="user", role="user", content="你好")
    response = await agent(msg)

    print(f"   Response: {response.content[:100]}...")
    print("\n✅ Agent call completed!")
    print("   请在 AgentScope Studio 的 Run TRACE 标签页查看 trace 数据")

asyncio.run(test_agent())