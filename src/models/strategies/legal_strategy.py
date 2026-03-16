"""法务策略：为后续法务岗位扩展预留独立规则空间。"""

from __future__ import annotations

import re
from typing import Any

from src.models.ai_service import AIModel
from src.models.generic_greeting_model import GenericGreetingModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class LegalStrategy(CandidateStrategy):
    """法务方向的基础策略。"""

    strategy_id = "legal"
    display_name = "法务"

    LEGAL_KEYWORDS = ["法务", "律师", "合同", "合规", "诉讼", "仲裁", "尽调", "风控", "法律"]

    def build_rule_precheck(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        jd_text: str,
        resume_text: str,
    ) -> dict[str, Any]:
        """构建法务方向的轻量规则预筛。"""
        normalized_jd = self._normalize_text(jd_text)
        normalized_resume = self._normalize_text(resume_text)
        required_keywords = [item for item in self.LEGAL_KEYWORDS if item in normalized_jd]
        matched_keywords = [item for item in required_keywords if item in normalized_resume]
        missing_keywords = [item for item in required_keywords if item not in matched_keywords]
        hard_gaps: list[str] = []
        if any(keyword in normalized_jd for keyword in ["法务", "律师"]) and not matched_keywords:
            hard_gaps.append("简历中未体现法务核心经历")
        if any(keyword in normalized_jd for keyword in ["前端", "后端", "开发"]) and "法务" not in normalized_jd:
            hard_gaps.append("岗位主体并非法务方向")
        cap_score = 65 if hard_gaps else 100
        return {
            "required_keywords": required_keywords,
            "matched_keywords": matched_keywords,
            "missing_keywords": missing_keywords,
            "hard_gaps": hard_gaps,
            "cap_score": cap_score,
            "must_not_recommend": bool(hard_gaps),
        }

    def apply_rule_postcheck(
        self,
        match_data: dict[str, Any],
        precheck: dict[str, Any],
        jd: JobDescription,
    ) -> dict[str, Any]:
        """用法务策略兜底 LLM 输出。"""
        result = dict(match_data)
        score = min(float(result.get("match_score", 0) or 0), float(precheck["cap_score"]))
        result["match_score"] = score
        result["match_level"] = "高" if score >= 80 else "中" if score >= 60 else "低"
        missing_skills = list(result.get("missing_skills", []) or [])
        for keyword in precheck["missing_keywords"]:
            if keyword not in missing_skills:
                missing_skills.append(keyword)
        result["missing_skills"] = missing_skills[:8]
        if precheck["must_not_recommend"] or score < 75:
            result["is_recommended"] = False
        return result

    def generate_greeting(
        self,
        ai_model: AIModel,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """法务方向使用更中性的通用招呼语模型。"""
        return GenericGreetingModel(ai_model, domain_label=self.display_name).generate_greeting(jd, resume, match_data)

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """按法务关键词粗判是否适合。"""
        text = self._normalize_text(" ".join([resume.target_position or "", resume.self_introduction or "", " ".join(resume.skills or [])]))
        return any(keyword in text for keyword in self.LEGAL_KEYWORDS)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower()).strip()


__all__ = ["LegalStrategy"]
