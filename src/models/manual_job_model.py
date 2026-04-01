"""Manual job analysis model for MVC architecture."""

from src.models.job_description import JobDescription
from src.models.job_match_result import JobMatchResult
from src.models.job_matching_model import JobMatchingModel
from src.models.resume_profile import ResumeProfile


class ManualJobModel:
    """Handle the manual JD -> LLM match -> greeting use case."""

    def __init__(self, matching_model: JobMatchingModel | None = None) -> None:
        """初始化手动 JD 分析模型。"""
        self.matching_model = matching_model or JobMatchingModel()

    def use_strategy(self, strategy_id: str, resume: ResumeProfile | None = None) -> None:
        """切换当前手动分析使用的策略。"""
        self.matching_model.set_strategy(strategy_id, resume)

    def use_llm_provider(self, provider: str) -> None:
        """切换当前手动分析使用的 LLM 提供方。"""
        self.matching_model.set_llm_provider(provider)

    def analyze_manual_job(self, jd_info: dict, resume: ResumeProfile) -> JobMatchResult | None:
        """Convert CLI input to a model object and analyze it with the LLM matcher."""
        job = JobDescription(
            job_id="manual_input",
            job_title=jd_info["job_title"],
            company_name=jd_info["company_name"],
            salary_range=jd_info["salary_range"],
            location=jd_info["location"],
            job_requirements=jd_info["job_requirements"],
            job_description=jd_info["job_description"],
            tags=jd_info["tags"],
            job_url=jd_info["job_url"],
        )
        return self.matching_model.analyze_match(job, resume=resume)


__all__ = ["ManualJobModel"]
