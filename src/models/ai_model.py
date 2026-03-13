"""MVC model export: AI chat client."""

from src.infrastructure.ai.zhipu_chat_client import ZhipuChatClient


class AIModel(ZhipuChatClient):
    """MVC-friendly alias for AI chat client."""


__all__ = ["AIModel"]
