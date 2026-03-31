"""Model layer exports for the MVC surface."""

from src.models.ai_service import AIModel, AIService
from src.models.boss_apply_facade import BossApplyFacade, BossApplyOptions
from src.models.job_apply_model import JobApplyModel, JobApplyRequest
from src.models.job_application_agent import AgentRunSummary, JobApplicationAgent, JobApplicationAgentRequest
from src.models.job_description import JobDescription
from src.models.job_match_result import JobMatchResult
from src.models.job_matching_model import JobMatchingModel
from src.models.job_repository import JobRepository
from src.models.job_search_model import JobSearchModel, JobSearchRequest, SearchCollectionSummary
from src.models.job_screening_model import JobScreeningModel
from src.models.manual_job_model import ManualJobModel
from src.models.resume_profile import ResumeProfile
from src.models.resume_store import ResumeStore

__all__ = [
    "AIService",
    "AIModel",
    "BossApplyFacade",
    "BossApplyOptions",
    "AgentRunSummary",
    "JobApplyModel",
    "JobApplyRequest",
    "JobApplicationAgent",
    "JobApplicationAgentRequest",
    "JobDescription",
    "JobMatchResult",
    "JobMatchingModel",
    "JobRepository",
    "JobSearchModel",
    "JobSearchRequest",
    "SearchCollectionSummary",
    "JobScreeningModel",
    "ManualJobModel",
    "ResumeProfile",
    "ResumeStore",
]
