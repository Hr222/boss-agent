"""AI 服务门面：给模型层提供统一的大模型调用入口。"""

from src.config.settings import Config
from src.infrastructure.ai.client_factory import AIClientFactory
from src.models.llm_prompt_builder import LLMPromptBuilder


class AIService:
    """面向业务层的 LLM 服务门面。"""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or Config.get_llm_provider()).strip().lower()
        self.client = AIClientFactory.create(self.provider)
        self.provider = self.client.provider_name

    def chat(self, messages: list, model: str | None = None, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        selected_model = model or self.client.default_match_model
        return self.client.chat(
            messages=messages,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def analyze_jd_match(
        self,
        jd_text: str,
        resume_text: str,
        rule_precheck: dict | None = None,
    ) -> str:
        messages = LLMPromptBuilder.build_jd_match_messages(jd_text, resume_text, rule_precheck)
        return self.chat(messages, temperature=0.3)


AIModel = AIService


__all__ = ["AIService", "AIModel"]
