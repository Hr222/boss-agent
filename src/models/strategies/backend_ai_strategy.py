"""后端与AI工程化策略：承接当前项目的主匹配逻辑。"""

from __future__ import annotations

import re
from typing import Any

from src.models.ai_model import AIModel
from src.models.greeting_model import GreetingModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class BackendAIStrategy(CandidateStrategy):
    """适用于后端、偏全栈、AI 工程化方向的匹配策略。"""

    strategy_id = "backend_ai"
    display_name = "后端与AI工程化"

    LANGUAGE_PATTERNS = {
        "Python": [r"\bpython\b"],
        "Java": [r"\bjava\b"],
        "Go": [r"\bgo\b", r"\bgolang\b"],
        "C/C++": [r"\bc\+\+\b", r"\bc/c\+\+\b", r"\bc语言\b", r"\bc\+\+开发\b"],
        "Rust": [r"\brust\b"],
        "JavaScript": [r"\bjavascript\b", r"\bjs\b"],
    }

    FRAMEWORK_PATTERNS = {
        "Django": [r"\bdjango\b"],
        "Flask": [r"\bflask\b"],
        "FastAPI": [r"\bfastapi\b"],
        "Tornado": [r"\btornado\b"],
        "Spring": [r"\bspring\b", r"\bspring boot\b"],
    }

    # AI 工程化相关能力单独抽取，避免被误归入传统语言/框架维度。
    AI_ENGINEERING_PATTERNS = {
        "LangChain": [r"\blangchain\b"],
        "RAG": [r"\brag\b", r"检索增强", r"检索增强生成"],
        "Prompt Engineering": [r"prompt engineering", r"提示词工程", r"prompt设计"],
        "Agent": [r"\bagent\b", r"智能体"],
        "OpenClaw": [r"\bopenclaw\b"],
        "AI Coding": [r"ai coding", r"ai编程", r"智能编码", r"copilot", r"claude", r"codex", r"deepseek", r"gemini"],
    }

    LANGUAGE_ECOSYSTEM_PATTERNS = {
        "Java": [r"\bspring\b", r"\bspring boot\b", r"jvm", r"java生态"],
        "Go": [r"\bgin\b", r"\bbeego\b", r"\bgo-zero\b", r"go生态"],
        "C/C++": [r"stl", r"内存管理", r"多线程", r"网络编程"],
        "JavaScript": [r"\bnode\.?js\b", r"\btypescript\b", r"前端工程化"],
        "Python": [r"\bdjango\b", r"\bflask\b", r"\bfastapi\b", r"\btornado\b"],
    }

    LANGUAGE_DEPTH_KEYWORDS = [
        "精通",
        "熟练",
        "扎实",
        "深入理解",
        "深刻理解",
        "底层",
        "原理",
        "源码",
        "虚拟机",
        "内存模型",
        "编译原理",
        "语言特性",
    ]

    def build_rule_precheck(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        jd_text: str,
        resume_text: str,
    ) -> dict[str, Any]:
        """复用当前后端主策略的规则预筛。"""
        normalized_jd = self._normalize_text(jd_text)
        normalized_resume = self._normalize_text(resume_text)
        required_languages = self._extract_required_items(normalized_jd, self.LANGUAGE_PATTERNS)
        matched_languages = [item for item in required_languages if self._contains_item(normalized_resume, self.LANGUAGE_PATTERNS[item])]
        missing_languages = [item for item in required_languages if item not in matched_languages]
        required_frameworks = self._extract_required_items(normalized_jd, self.FRAMEWORK_PATTERNS)
        matched_frameworks = [item for item in required_frameworks if self._contains_item(normalized_resume, self.FRAMEWORK_PATTERNS[item])]
        missing_frameworks = [item for item in required_frameworks if item not in matched_frameworks]
        required_ai_skills = self._extract_required_items(normalized_jd, self.AI_ENGINEERING_PATTERNS)
        matched_ai_skills = [
            item for item in required_ai_skills if self._contains_item(normalized_resume, self.AI_ENGINEERING_PATTERNS[item])
        ]
        missing_ai_skills = [item for item in required_ai_skills if item not in matched_ai_skills]
        resume_years = self._parse_years(resume.years_of_experience)
        required_years = self._extract_required_years(normalized_jd)
        years_gap = max(required_years - resume_years, 0)
        hard_language_gaps = [item for item in missing_languages if self._is_hard_language_requirement(normalized_jd, item)]
        soft_language_gaps = [item for item in missing_languages if item not in hard_language_gaps]

        hard_gaps: list[str] = []
        if hard_language_gaps:
            hard_gaps.append(f"缺少关键语言能力: {', '.join(hard_language_gaps)}")
        if years_gap >= 1:
            hard_gaps.append(f"年限不足: JD要求约{required_years}年，简历为{resume_years}年")
        if self._is_non_backend_primary_role(jd, hard_language_gaps):
            hard_gaps.append("岗位主体并非后端与AI工程化方向")
        major_framework_gaps = [item for item in missing_frameworks if item in {"Spring", "Tornado"}]
        if major_framework_gaps:
            hard_gaps.append(f"缺少关键框架/平台能力: {', '.join(major_framework_gaps)}")

        cap_score = 100
        if len(hard_gaps) >= 2:
            cap_score = min(cap_score, 65)
        elif hard_language_gaps:
            cap_score = min(cap_score, 70)
        elif years_gap >= 1:
            cap_score = min(cap_score, 75)
        elif major_framework_gaps:
            cap_score = min(cap_score, 75)
        elif soft_language_gaps:
            cap_score = min(cap_score, 85 if resume_years >= 5 else 80)

        must_not_recommend = len(hard_gaps) > 0 or cap_score < 75
        return {
            "required_languages": required_languages,
            "matched_languages": matched_languages,
            "missing_languages": missing_languages,
            "hard_language_gaps": hard_language_gaps,
            "soft_language_gaps": soft_language_gaps,
            "required_frameworks": required_frameworks,
            "matched_frameworks": matched_frameworks,
            "missing_frameworks": missing_frameworks,
            "required_ai_skills": required_ai_skills,
            "matched_ai_skills": matched_ai_skills,
            "missing_ai_skills": missing_ai_skills,
            "required_years": required_years,
            "resume_years": resume_years,
            "years_gap": years_gap,
            "hard_gaps": hard_gaps,
            "cap_score": cap_score,
            "must_not_recommend": must_not_recommend,
        }

    def apply_rule_postcheck(
        self,
        match_data: dict[str, Any],
        precheck: dict[str, Any],
        jd: JobDescription,
    ) -> dict[str, Any]:
        """把后端策略的规则约束落回 LLM 输出。"""
        result = dict(match_data)
        raw_score = float(result.get("match_score", 0) or 0)
        final_score = min(raw_score, float(precheck["cap_score"]))
        result["match_score"] = final_score
        result["match_level"] = self._score_to_level(final_score)
        missing_skills = list(result.get("missing_skills", []) or [])
        for item in precheck["missing_languages"] + precheck["missing_frameworks"] + precheck["missing_ai_skills"]:
            if item not in missing_skills:
                missing_skills.append(item)
        result["missing_skills"] = missing_skills[:8]
        matched_skills = list(result.get("matched_skills", []) or [])
        for item in precheck["matched_ai_skills"]:
            if item not in matched_skills:
                matched_skills.append(item)
        result["matched_skills"] = matched_skills[:8]
        if precheck["must_not_recommend"] or final_score < 75:
            result["is_recommended"] = False
        hard_gaps = precheck["hard_gaps"]
        if hard_gaps:
            analysis = (result.get("analysis", "") or "").strip()
            gap_text = "；".join(hard_gaps)
            if gap_text not in analysis:
                result["analysis"] = f"{analysis} 规则预筛提示：{gap_text}。".strip()
            suggestions = list(result.get("suggestions", []) or [])
            suggestion = f"优先补齐硬性缺口：{gap_text}"
            if suggestion not in suggestions:
                suggestions.insert(0, suggestion)
            result["suggestions"] = suggestions[:4]
        return result

    def generate_greeting(
        self,
        ai_model: AIModel,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """后端与 AI 工程化方向沿用当前成熟的招呼语模型。"""
        return GreetingModel(ai_model).generate_greeting(jd, resume, match_data)

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """按简历目标与技能粗判当前策略是否适合。"""
        text = self._normalize_text(
            " ".join(
                [
                    resume.target_position or "",
                    resume.self_introduction or "",
                    " ".join(resume.skills or []),
                    " ".join(resume.advantages or []),
                ]
            )
        )
        keywords = [
            "java",
            "python",
            "spring",
            "django",
            "fastapi",
            "后端",
            "全栈",
            "ai",
            "langchain",
            "rag",
            "openclaw",
            "agent",
            "ai coding",
            "prompt engineering",
        ]
        return any(keyword in text for keyword in keywords)

    def _extract_required_items(self, text: str, pattern_map: dict[str, list[str]]) -> list[str]:
        return [item for item, patterns in pattern_map.items() if self._contains_item(text, patterns)]

    def _contains_item(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _extract_required_years(self, text: str) -> int:
        patterns = [r"(\d+)\s*年以上", r"至少\s*(\d+)\s*年", r"(\d+)\s*年及以上", r"(\d+)\s*-\s*(\d+)\s*年", r"(\d+)\+\s*年"]
        years: list[int] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                groups = [int(group) for group in match.groups() if group]
                if groups:
                    years.append(min(groups))
        return max(years) if years else 0

    def _parse_years(self, value: str) -> int:
        match = re.search(r"(\d+)", value or "")
        return int(match.group(1)) if match else 0

    def _is_non_backend_primary_role(self, jd: JobDescription, hard_language_gaps: list[str]) -> bool:
        title = self._normalize_text(jd.job_title)
        if any(keyword in title for keyword in ["后端", "全栈", "python", "java", "golang", "go", "ai"]):
            return False
        if any(keyword in title for keyword in ["前端", "react", "vue", "法务", "律师", "合规"]):
            return True
        return bool(hard_language_gaps) and any(keyword in title for keyword in ["c++", "rust"])

    def _is_hard_language_requirement(self, normalized_jd: str, language: str) -> bool:
        aliases = self.LANGUAGE_PATTERNS.get(language, [])
        ecosystem_patterns = self.LANGUAGE_ECOSYSTEM_PATTERNS.get(language, [])
        for pattern in aliases:
            for match in re.finditer(pattern, normalized_jd, flags=re.IGNORECASE):
                start = max(0, match.start() - 30)
                end = min(len(normalized_jd), match.end() + 30)
                context = normalized_jd[start:end]
                if any(keyword in context for keyword in self.LANGUAGE_DEPTH_KEYWORDS):
                    return True
                if any(re.search(item, context, flags=re.IGNORECASE) for item in ecosystem_patterns):
                    return True
        return False

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower()).strip()

    def _score_to_level(self, score: float) -> str:
        if score >= 80:
            return "高"
        if score >= 60:
            return "中"
        return "低"


__all__ = ["BackendAIStrategy"]
