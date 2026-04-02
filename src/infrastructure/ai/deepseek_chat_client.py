"""DeepSeek 客户端。"""

import json
from typing import Any, Optional
from urllib import request

from src.config.settings import Config
from src.infrastructure.ai.base_chat_client import BaseChatClient


class DeepSeekChatClient(BaseChatClient):
    """基于 OpenAI 兼容接口的 DeepSeek 客户端。"""

    provider_name = "deepseek"
    default_match_model = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.get_llm_api_key("deepseek")
        if not self.api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")
        self.base_url = Config.DEEPSEEK_BASE_URL.rstrip("/")

    def chat(
        self,
        messages: list,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise Exception(f"DeepSeek调用失败: {e}")
        return self._extract_response_text(response_data)

    def _extract_response_text(self, response: Any) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except Exception as e:
            raise Exception(f"响应结构异常，无法读取 DeepSeek content: {e}")
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise Exception("DeepSeek 模型返回为空")
