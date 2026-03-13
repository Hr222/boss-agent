"""岗位策略抽象：隔离不同方向的匹配规则与招呼语逻辑。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.models.ai_model import AIModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile


class CandidateStrategy(ABC):
    """定义岗位策略的统一接口。"""

    strategy_id = "base"
    display_name = "基础策略"

    @abstractmethod
    def build_rule_precheck(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        jd_text: str,
        resume_text: str,
    ) -> dict[str, Any]:
        """构建规则预筛结果。"""

    @abstractmethod
    def apply_rule_postcheck(
        self,
        match_data: dict[str, Any],
        precheck: dict[str, Any],
        jd: JobDescription,
    ) -> dict[str, Any]:
        """对 LLM 输出做策略层兜底。"""

    @abstractmethod
    def generate_greeting(
        self,
        ai_model: AIModel,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """生成策略对应的招呼语。"""

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """当前策略是否适合这份简历。默认返回 False，由具体策略覆盖。"""
        return False


__all__ = ["CandidateStrategy"]
