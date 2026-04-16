"""测试 AgentScope ReActAgent 的 tracing"""
import asyncio
import os

os.environ['AGENTSCOPE_STUDIO_URL'] = 'http://localhost:3000'
os.environ['KIMI_API_KEY'] = 'sk-tukbjrbeaxDKcsTyDIhGPB7zbO08Nd0BeVgIdAGJtURs9FpG'

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import ChatResponse


class MockModel:
    """模拟 Kimi API 模型"""
    def __init__(self, api_key, model_name):
        self.api_key = api_key
        self.model_name = model_name
        self.stream = False  # ReActAgent 需要这个属性

    async def __call__(self, messages, stream=False, **kwargs):
        import httpx
        import time

        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # 转换 messages 格式
        msgs = []
        for m in messages:
            if hasattr(m, 'content'):
                msgs.append({'role': m.role, 'content': m.content})
            else:
                msgs.append({'role': 'user', 'content': str(m)})

        payload = {
            "model": self.model_name,
            "messages": msgs,
            "stream": False,
            "max_tokens": kwargs.get('max_tokens', 100)
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                usage = result.get('usage', {})

                # 返回 ChatResponse（字典类型）
                return ChatResponse(
                    content=content,
                    id=f"mock_{int(time.time())}",
                    usage=usage,
                    metadata={}
                )
            else:
                raise Exception(f"API error: {response.status_code}")


async def main():
    import agentscope

    # 初始化 Studio（可选，但可以指定项目名）
    agentscope.init(
        studio_url="http://localhost:3000",
        project="doc_revewer",
        name="test_react"
    )

    # 创建 Agent - 使用 ReActAgent
    agent = ReActAgent(
        name="TestAgent",
        sys_prompt="你是一个有帮助的助手。",
        model=MockModel(
            api_key=os.environ['KIMI_API_KEY'],
            model_name="moonshot-v1-8k"
        ),
        formatter=OpenAIChatFormatter(),
        memory=InMemoryMemory(),
    )

    # 发送消息
    user_msg = Msg("user", "请用一句话介绍你自己", "user")

    # 获取回复
    response = await agent(user_msg)

    print(f"Response: {response.content}")
    print("✅ 请在 Studio 查看 trace!")


asyncio.run(main())
