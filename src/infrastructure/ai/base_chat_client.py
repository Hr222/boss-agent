"""通用聊天客户端基类。"""


class BaseChatClient:
    """不同 LLM 提供方的共享接口。"""

    provider_name = "unknown"
    default_match_model = ""

    def chat(
        self,
        messages: list,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        raise NotImplementedError
