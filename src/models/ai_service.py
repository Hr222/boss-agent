"""AI 服务门面：给模型层提供统一的大模型调用入口。"""

from src.infrastructure.ai.zhipu_chat_client import ZhipuChatClient


class AIService(ZhipuChatClient):
    """面向业务模型的大模型服务门面。"""


# 兼容旧命名，避免现有调用链失效。
AIModel = AIService


__all__ = ["AIService", "AIModel"]
