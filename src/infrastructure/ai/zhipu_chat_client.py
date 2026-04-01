"""智谱 AI 客户端。"""

from typing import Any, Optional

from zai import ZaiClient

from src.config.settings import Config
from src.infrastructure.ai.base_chat_client import BaseChatClient


class ZhipuChatClient(BaseChatClient):
    """智谱 AI 客户端。"""

    provider_name = "zhipu"
    default_match_model = "glm-5"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.get_llm_api_key("zhipu")
        if not self.api_key:
            raise ValueError("请设置 ZAI_API_KEY 或 ZHIPUAI_API_KEY 环境变量")

        self.client = ZaiClient(
            api_key=self.api_key,
            base_url=Config.ZAI_BASE_URL,
        )

    def chat(
        self,
        messages: list,
        model: str = "glm-5",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
            )
            return self._extract_response_text(response)
        except Exception as e:
            raise Exception(f"智谱AI调用失败: {e}")

    def _extract_response_text(self, response: Any) -> str:
        """兼容不同响应结构，尽量稳定提取模型文本。"""
        try:
            message = response.choices[0].message
        except Exception as e:
            raise Exception(f"响应结构异常，无法读取 message: {e}")

        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    text_parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text"):
                        text_parts.append(str(item["text"]).strip())
                    elif item.get("content"):
                        text_parts.append(str(item["content"]).strip())
                    continue
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text:
                    text_parts.append(str(text).strip())
            merged = "\n".join(part for part in text_parts if part)
            if merged.strip():
                return merged.strip()

        raise Exception(f"模型返回为空，finish_reason={getattr(response.choices[0], 'finish_reason', None)}")
