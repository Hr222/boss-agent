"""智谱 AI 客户端。"""

import random
import time
from typing import Any, Optional

from zai import ZaiClient

from src.config.settings import Config
from src.infrastructure.ai.base_chat_client import BaseChatClient


class LLMTemporaryUnavailableError(Exception):
    """表示可恢复的临时性 LLM 错误，如限流或服务过载。"""


class ZhipuChatClient(BaseChatClient):
    """智谱 AI 客户端。"""

    provider_name = "zhipu"
    default_match_model = "glm-5"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.get_llm_api_key("zhipu")
        if not self.api_key:
            raise ValueError("请设置 ZAI_API_KEY 或 ZHIPUAI_API_KEY 环境变量")
        self.retry_attempts = max(1, int(Config.ZHIPU_RETRY_ATTEMPTS))
        self.retry_base_delay = max(0.5, float(Config.ZHIPU_RETRY_BASE_DELAY))
        self.retry_max_delay = max(self.retry_base_delay, float(Config.ZHIPU_RETRY_MAX_DELAY))
        self.rate_limit_cooldown = max(0.0, float(Config.ZHIPU_RATE_LIMIT_COOLDOWN))
        self._blocked_until = 0.0

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
        last_error: Exception | None = None
        self._sleep_if_rate_limited()
        for attempt_index in range(self.retry_attempts):
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
                last_error = e
                if not self._is_retryable_error(e) or attempt_index >= self.retry_attempts - 1:
                    if self._is_retryable_error(e):
                        self._blocked_until = max(self._blocked_until, time.time() + self.rate_limit_cooldown)
                        raise LLMTemporaryUnavailableError(f"智谱AI临时限流/过载: {e}") from e
                    raise Exception(f"智谱AI调用失败: {e}") from e
                delay_seconds = self._calculate_retry_delay(attempt_index)
                print(
                    f"[llm:zhipu] 调用触发限流/过载，"
                    f"{delay_seconds:.1f}s 后重试 "
                    f"({attempt_index + 2}/{self.retry_attempts})"
                )
                time.sleep(delay_seconds)
        raise LLMTemporaryUnavailableError(f"智谱AI临时限流/过载: {last_error}")

    def _is_retryable_error(self, error: Exception) -> bool:
        text = str(error).lower()
        retry_markers = (
            "429",
            '"code":"1305"',
            '"code": "1305"',
            "temporarily overloaded",
            "rate limit",
            "too many requests",
            "service unavailable",
        )
        return any(marker in text for marker in retry_markers)

    def _calculate_retry_delay(self, attempt_index: int) -> float:
        base_delay = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt_index))
        jitter = random.uniform(0, min(1.0, base_delay * 0.2))
        return min(self.retry_max_delay, base_delay + jitter)

    def _sleep_if_rate_limited(self) -> None:
        remaining_seconds = self._blocked_until - time.time()
        if remaining_seconds <= 0:
            return
        print(f"[llm:zhipu] 进入限流冷却，等待 {remaining_seconds:.1f}s 后继续")
        time.sleep(remaining_seconds)
        self._blocked_until = 0.0

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
