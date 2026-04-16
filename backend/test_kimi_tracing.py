"""测试 Kimi API 调用并追踪（ReActAgent + KimiHTTPChatModel）"""
import os
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend))

os.environ["AGENTSCOPE_STUDIO_URL"] = "http://localhost:3000"
os.environ["USE_AGENTSCOPE"] = "true"

print("Initializing AgentScope...")
import agentscope

agentscope.init(studio_url="http://localhost:3000")
print("✅ AgentScope initialized")

from config import KIMI_API_KEY, KIMI_TEXT_MODEL
from agents.react_llm_bridge import create_react_backend

agent = create_react_backend(
    provider_type="moonshot",
    api_key=KIMI_API_KEY,
    model=KIMI_TEXT_MODEL,
)

print(f"Making LLM call using Kimi ({KIMI_TEXT_MODEL})...")

try:
    result = agent.call_llm(
        system="你是一个专业的文档审查助手。",
        user="请用一句话介绍自己。",
    )
    print(f"✅ Success: {result[:100]}...")
except Exception as e:
    print(f"❌ Error: {e}")

print("📊 Check Studio for trace!")
