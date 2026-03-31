"""岗位策略抽象：隔离不同方向的匹配规则与招呼语逻辑。"""

from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any

from src.models.ai_service import AIModel
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

    def generate_greeting(
        self,
        ai_model: AIModel,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """生成策略对应的招呼语。"""
        messages = [
            {"role": "system", "content": self.get_greeting_system_prompt()},
            {"role": "user", "content": self.build_greeting_prompt(jd, resume, match_data)},
        ]
        result = ai_model.chat(messages, temperature=self.get_greeting_temperature(), max_tokens=self.get_greeting_max_tokens())
        is_valid, issues = self.validate_greeting_output(result)
        if not is_valid:
            result = self.rewrite_greeting_with_feedback(ai_model, messages, result, issues)
        return self.finalize_greeting_text(result)

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """当前策略是否适合这份简历。默认返回 False，由具体策略覆盖。"""
        return False

    @abstractmethod
    def get_greeting_system_prompt(self) -> str:
        """返回岗位对应的系统提示词。"""

    @abstractmethod
    def build_greeting_prompt(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """构造岗位对应的招呼语用户提示词。"""

    def get_greeting_temperature(self) -> float:
        return 0.6

    def get_greeting_max_tokens(self) -> int:
        return 800

    def validate_greeting_output(self, text: str) -> tuple[bool, list[str]]:
        return True, []

    def rewrite_greeting_with_feedback(
        self,
        ai_model: AIModel,
        messages: list[dict[str, str]],
        draft: str,
        issues: list[str],
    ) -> str:
        return draft

    def finalize_greeting_text(self, text: str) -> str:
        return (text or "").strip()

    def build_jd_text(self, jd: JobDescription) -> str:
        parts = [
            jd.job_requirements or "",
            jd.job_description or "",
            ", ".join(jd.tags or []),
        ]
        return "\n".join(part for part in parts if part).strip()

    def build_resume_text(self, resume: ResumeProfile) -> str:
        lines = [
            f"姓名: {resume.name}",
            f"目标职位: {resume.target_position}",
            f"期望地点: {resume.target_location}",
            f"工作年限: {resume.years_of_experience}",
        ]
        if resume.skills:
            lines.extend(["", "技能:", ", ".join(resume.skills)])
        if resume.advantages:
            lines.extend(["", "个人优势:"])
            lines.extend(f"- {item}" for item in resume.advantages)
        if resume.self_introduction:
            lines.extend(["", "自我介绍:", resume.self_introduction])
        if resume.work_experience:
            lines.extend(["", "工作经历:"])
            for work in resume.work_experience:
                end_date = work.end_date or "至今"
                lines.append(f"- {work.company} | {work.position} | {work.start_date} - {end_date}")
                lines.append(f"  {work.description}")
        if resume.project_experience:
            lines.extend(["", "项目经历:"])
            for project in resume.project_experience:
                lines.append(f"- {project.name} | {project.role}")
                if project.technologies:
                    lines.append(f"  技术栈: {', '.join(project.technologies)}")
                lines.append(f"  {project.description}")
        return "\n".join(lines).strip()

    def count_visible_chars(self, text: str) -> int:
        return len(re.sub(r"\s+", "", text or ""))

    def split_paragraphs(self, text: str) -> list[str]:
        return [part.strip() for part in re.split(r"\n\s*\n|\n", text or "") if part.strip()]


__all__ = ["CandidateStrategy"]
