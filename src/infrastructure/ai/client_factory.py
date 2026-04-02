"""LLM 客户端工厂。"""

from src.infrastructure.ai.base_chat_client import BaseChatClient
from src.infrastructure.ai.deepseek_chat_client import DeepSeekChatClient
from src.infrastructure.ai.zhipu_chat_client import ZhipuChatClient


class AIClientFactory:
    """按 provider 创建具体客户端。"""

    @staticmethod
    def create(provider: str) -> BaseChatClient:
        normalized = (provider or "zhipu").strip().lower()
        if normalized == "deepseek":
            return DeepSeekChatClient()
        return ZhipuChatClient()
