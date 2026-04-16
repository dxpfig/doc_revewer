"""测试 AgentScope 追踪功能 - 使用 Kimi + ReActAgent"""
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend))

os.environ["AGENTSCOPE_STUDIO_URL"] = "http://localhost:3000"
os.environ.setdefault("KIMI_API_KEY", "")

print("Initializing AgentScope...")
import agentscope

agentscope.init(
    studio_url="http://localhost:3000",
    project="doc_revewer",
    name="test_tracing",
)
print(f"✅ AgentScope initialized, run_id: {agentscope._config.run_id}")

from agents.react_llm_bridge import create_react_backend

key = os.environ.get("KIMI_API_KEY")
if not key:
    print("跳过：未设置 KIMI_API_KEY")
    sys.exit(0)

agent = create_react_backend(
    provider_type="moonshot",
    base_url="https://api.moonshot.cn/v1",
    api_key=key,
    model="moonshot-v1-8k",
)

print("Making LLM call with tracing...")
try:
    result = agent.call_llm(
        system="你是一个有帮助的助手。",
        user="请用一句话介绍你自己。",
    )
    print(f"✅ Success: {result[:100]}...")
except Exception as e:
    print(f"❌ Error: {e}")

print("✅ Tracing should be recorded!")
print("📊 Please check Studio at http://localhost:3000/projects/doc_revewer")
print(f"   Run ID: {agentscope._config.run_id}")
