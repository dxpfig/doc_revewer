"""测试 AgentScope 追踪功能 - 使用后端环境（ReAct 桥接）"""
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend))

os.environ["AGENTSCOPE_STUDIO_URL"] = "http://localhost:3000"
os.environ["USE_AGENTSCOPE"] = "true"
os.environ["PYTHONPATH"] = str(_backend)

print("Initializing AgentScope...")
import agentscope

agentscope.init(studio_url="http://localhost:3000")
print("✅ AgentScope initialized")

from agents.react_llm_bridge import create_react_backend

agent = create_react_backend(
    provider_type="openai",
    base_url="https://api.openai.com/v1",
    api_key="sk-test-key-for-tracing-test",
    model="gpt-4o-mini",
)

print("Making LLM call with tracing...")

try:
    result = agent.call_llm(
        system="You are a helpful assistant.",
        user="Say 'hello' in one word.",
    )
    print(f"Success: {result[:50]}")
except Exception as e:
    print(f"Expected error (due to invalid key): {type(e).__name__}")

print("✅ Tracing should be recorded!")
print("📊 Please check Studio for the trace!")
