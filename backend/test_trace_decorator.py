"""使用 AgentScope trace 装饰器进行 tracing 测试"""
import os

os.environ['AGENTSCOPE_STUDIO_URL'] = 'http://localhost:3000'
os.environ['KIMI_API_KEY'] = 'sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG'

import agentscope

# 初始化 Studio
agentscope.init(
    studio_url="http://localhost:3000",
    project="doc_revewer",
    name="trace_test"
)

# 使用 trace 装饰器
from agentscope.tracing import trace


@trace(name="kimi_llm_call")
def call_kimi():
    """模拟 LLM 调用"""
    import httpx

    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ['KIMI_API_KEY']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": "你是一个有帮助的助手。"},
            {"role": "user", "content": "请用一句话介绍你自己。"}
        ],
        "max_tokens": 50
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise Exception(f"API error: {response.status_code}")


# 执行调用
print("Calling Kimi API with tracing...")
result = call_kimi()
print(f"Result: {result}")
print("✅ 请在 Studio 查看 trace!")
print(f"Run ID: {agentscope._config.run_id}")
