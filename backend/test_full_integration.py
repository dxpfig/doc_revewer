"""
AgentScope 集成测试
"""
import asyncio
import os

# 设置环境变量
os.environ['KIMI_API_KEY'] = 'sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG'
os.environ['AGENTSCOPE_STUDIO_URL'] = 'http://localhost:3000'

import agentscope
from agentscope.message import Msg
from agentscope.agent import AgentBase
from agentscope.tracing import trace


class KimiLLM:
    """Kimi LLM 封装"""

    def __init__(self, api_key: str, model: str = "moonshot-v1-8k"):
        self.api_key = api_key
        self.model = model

    @trace(name="kimi_chat")
    async def chat(self, messages: list, **kwargs) -> str:
        import httpx

        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 100)
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise Exception(f"API error: {response.status_code}")


class TestAgent(AgentBase):
    """测试 Agent"""

    def __init__(self, name: str, kimi_llm: KimiLLM):
        super().__init__()
        self.name = name
        self.kimi_llm = kimi_llm

    @trace(name="agent_reply")
    async def reply(self, msg: Msg) -> Msg:
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手。"},
            {"role": "user", "content": msg.content}
        ]
        response = await self.kimi_llm.chat(messages)
        return Msg(name=self.name, content=response, role="assistant")


async def main():
    # 1. 初始化 AgentScope
    agentscope.init(
        studio_url="http://localhost:3000",
        project="doc_revewer",
        name="full_test"
    )

    print("=" * 50)
    print("AgentScope 集成测试")
    print("=" * 50)
    print(f"Project: {agentscope._config.project}")
    print(f"Run ID: {agentscope._config.run_id}")
    print("=" * 50)

    # 2. 创建 Agent
    kimi_llm = KimiLLM(api_key=os.environ['KIMI_API_KEY'])
    agent = TestAgent(name="TestAgent", kimi_llm=kimi_llm)

    # 3. 发送消息
    print("\n发送测试消息...")
    msg = Msg("user", "请用一句话介绍你自己", "user")
    response = await agent(msg)

    print(f"Agent 回复: {response.content}")
    print("\n" + "=" * 50)
    print("✅ 测试完成!")
    print(f"请在 Studio 查看: http://localhost:3000")
    print(f"Project: doc_revewer")
    print(f"Run ID: {agentscope._config.run_id}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
