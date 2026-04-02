"""
LLM Service - LLM 调用封装
提供模型发现、测试、调用逻辑
"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import ModelProvider
from agents.react_llm_bridge import ReactLLMBackend

logger = logging.getLogger(__name__)


class LLMService:
    """Service for managing LLM providers and calls"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._active_provider: Optional[ModelProvider] = None

    async def get_active_provider(self) -> Optional[ModelProvider]:
        """获取当前活跃的 LLM Provider"""
        result = await self.db.execute(
            select(ModelProvider)
            .where(ModelProvider.is_active == True)
            .order_by(ModelProvider.created_at.desc())
        )
        provider = result.scalars().first()
        if provider:
            self._active_provider = provider
        return provider

    async def get_provider_by_id(self, provider_id: int) -> Optional[ModelProvider]:
        """根据 ID 获取 Provider"""
        result = await self.db.execute(
            select(ModelProvider).where(ModelProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_all_providers(self) -> List[ModelProvider]:
        """获取所有 Provider"""
        result = await self.db.execute(
            select(ModelProvider).order_by(ModelProvider.created_at.desc())
        )
        return result.scalars().all()

    async def set_active_provider(self, provider_id: int) -> bool:
        """设置活跃的 Provider"""
        # 先禁用所有
        providers = await self.get_all_providers()
        for p in providers:
            p.is_active = False

        # 启用指定 provider
        provider = await self.get_provider_by_id(provider_id)
        if not provider:
            return False

        provider.is_active = True
        await self.db.commit()
        self._active_provider = provider
        return True

    def create_agent(
        self,
        provider: Optional[ModelProvider] = None,
        model: Optional[str] = None
    ) -> ReactLLMBackend:
        """
        从 Provider 创建 ReAct + ChatModel 桥接后端

        Args:
            provider: ModelProvider 实例
            model: 覆盖默认模型

        Returns:
            ReactLLMBackend 实例
        """
        p = provider or self._active_provider
        if not p:
            raise ValueError("No active LLM provider configured")

        return ReactLLMBackend(
            provider_type=p.provider_type,
            base_url=p.base_url,
            api_key=p.api_key,
            model=model or p.llm_model,
        )

    def create_ocr_agent(
        self,
        provider: Optional[ModelProvider] = None
    ) -> ReactLLMBackend:
        """
        创建用于 OCR 的 Vision 模型桥接（使用 ocr_model）

        Args:
            provider: ModelProvider 实例

        Returns:
            ReactLLMBackend 实例 (使用 ocr_model)
        """
        p = provider or self._active_provider
        if not p:
            raise ValueError("No active LLM provider configured")

        if not p.ocr_model:
            raise ValueError("No OCR model configured for this provider")

        return ReactLLMBackend(
            provider_type=p.provider_type,
            base_url=p.base_url,
            api_key=p.api_key,
            model=p.ocr_model,
        )

    async def test_provider(
        self,
        provider: ModelProvider
    ) -> Dict[str, Any]:
        """
        测试 LLM Provider 连接

        Args:
            provider: ModelProvider 实例

        Returns:
            测试结果
        """
        try:
            agent = self.create_agent(provider)
            # 发送简单测试请求
            response = agent.call_llm(
                system="你是一个有帮助的助手。",
                user="请回复 'OK' 如果你收到这条消息。",
                temperature=0.1,
                max_tokens=10
            )

            if response and "OK" in response.upper():
                return {
                    "success": True,
                    "message": "Connection successful",
                    "model": provider.llm_model,
                    "response_preview": response[:100]
                }
            else:
                return {
                    "success": False,
                    "message": "Unexpected response",
                    "response_preview": response[:100] if response else ""
                }

        except Exception as e:
            logger.error(f"Provider test failed: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }

    async def call_llm(
        self,
        system: str,
        user: str,
        **kwargs
    ) -> str:
        """
        便捷方法：直接调用 LLM

        Args:
            system: 系统提示词
            user: 用户输入
            **kwargs: 其他参数 (temperature, max_tokens 等)

        Returns:
            LLM 响应
        """
        if not self._active_provider:
            await self.get_active_provider()

        agent = self.create_agent()
        return agent.call_llm(system, user, **kwargs)

    @staticmethod
    def discover_models(provider_type: str, base_url: Optional[str] = None) -> List[str]:
        """
        发现可用的模型列表

        Args:
            provider_type: provider 类型
            base_url: 自定义 base_url

        Returns:
            模型列表
        """
        if provider_type == "openai":
            return [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-3.5-turbo"
            ]
        elif provider_type == "anthropic":
            return [
                "claude-3-5-sonnet-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307"
            ]
        elif provider_type == "deepseek":
            return [
                "deepseek-chat",
                "deepseek-coder"
            ]
        elif provider_type == "minimax":
            return [
                "abab6.5s-chat",
                "abab6.5g-chat"
            ]
        elif provider_type == "moonshot":
            return [
                "moonshot-v1-8k",           # 文本模型
                "moonshot-v1-32k",          # 长文本模型
                "moonshot-v1-8k-vision-preview",  # 视觉模型 (OCR)
            ]
        else:
            return ["gpt-3.5-turbo"]  # 默认


# 便捷函数
async def get_llm_service(db: AsyncSession) -> LLMService:
    """获取 LLM Service 实例"""
    return LLMService(db)