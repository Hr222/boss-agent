"""法务策略：为后续法务岗位扩展预留独立规则空间。"""

from __future__ import annotations

import re
from typing import Any

from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class LegalStrategy(CandidateStrategy):
    """法务方向的基础策略。"""

    strategy_id = "legal"
    display_name = "法务"
    GREETING_POSTSCRIPT = (
        "PS: 该招呼语由我编写的求职 Agent 自动发送。"
        "目前正在研发 OpenClaw 求职版，会先基于 LLM 分析岗位 JD，"
        "确认与贵司用人画像基本匹配后再发出。"
        "如收到回复，后续将由我本人真人沟通。"
    )

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
        if any(keyword in normalized_jd for keyword in ["前端", "后端", "开发", "ui", "ux", "设计师", "视觉设计", "交互设计"]) and "法务" not in normalized_jd:
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

    def get_greeting_system_prompt(self) -> str:
        return "你擅长将岗位重点和候选人的真实经历压缩成自然、克制、像真人首条消息的中文表达。你不会虚构经历，也不会输出模板化求职话术。"

    def build_greeting_prompt(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        matched_experience = " | ".join(match_data.get("matched_experience", []) or []) or "无"
        matched_skills = ", ".join(match_data.get("matched_skills", []) or []) or "无"
        advantages = " | ".join(match_data.get("advantages", []) or []) or "无"
        resume_text = " | ".join(
            item.strip()
            for item in [resume.self_introduction or "", *resume.advantages[:4]]
            if item.strip()
        ) or "无"
        return f"""你现在要模拟 Boss 直聘上的首条打招呼消息。

【策略方向】
{self.display_name}

【岗位】
职位: {jd.job_title}
公司: {jd.company_name}
职位要求: {jd.job_requirements or '无'}
职位描述: {jd.job_description or '无'}

【候选人真实信息】
匹配技能: {matched_skills}
匹配经历: {matched_experience}
优势: {advantages}
简历摘要: {resume_text}

【硬约束】
1. 只输出最终打招呼语，不要解释，不要分点。
2. 长度控制在 110 到 170 个中文字符之间。
3. 语气像真人发出的第一条消息，不能像简历总结。
4. 只能基于上面的真实信息，不要虚构经历和量化结果。
5. 不要写“希望有机会”“期待沟通”“非常感兴趣”“我相信我能胜任”。
6. 直接围绕岗位最核心的 1 到 2 个要求来写。
7. 不要出现公司名、项目名、模板化寒暄。
8. 不要面面俱到，不要把所有匹配点都写进去。
9. 优先写做过的事和结果，不要罗列技能名。
10. 最后一句不要写求职总结，应自然落在做过的工作场景或能力补充上。
11. 严禁附加 PS、括号说明、Agent 自述、真人回复说明。

请直接返回最终文案，不要解释。"""

    def get_greeting_max_tokens(self) -> int:
        return 512

    def finalize_greeting_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "")).strip(" ，,。")
        patterns = [
            r"^(您好[，,]?\s*|你好[，,]?\s*|嗨[，,]?\s*)",
            r"(希望有机会[^。！？!?.]*[。！？!?.]?)",
            r"(期待[^。！？!?.]*[。！？!?.]?)",
            r"(非常感兴趣[^。！？!?.]*[。！？!?.]?)",
            r"(我相信[^。！？!?.]*[。！？!?.]?)",
            r"\(?PS[:：][^)]*\)?",
            r"（?该招呼语由我制作的求职agent[^）]*）?",
            r"（?后续将由我本人真人回复[^）]*）?",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)
        cleaned = cleaned.strip(" ，,。")
        sentence_parts = [item.strip() for item in re.split(r"[。！？]", cleaned) if item.strip()]
        if len(sentence_parts) > 3:
            cleaned = "。".join(sentence_parts[:3])
        if len(cleaned) > 185:
            cleaned = cleaned[:185].rstrip("，,、 ")
        if cleaned and cleaned[-1] not in "。！？":
            cleaned += "。"
        postscript = self.GREETING_POSTSCRIPT.strip()
        return cleaned if not postscript else f"{cleaned}\n({postscript})"

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """按法务关键词粗判是否适合。"""
        text = self._normalize_text(" ".join([resume.target_position or "", resume.self_introduction or "", " ".join(resume.skills or [])]))
        return any(keyword in text for keyword in self.LEGAL_KEYWORDS)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower()).strip()


__all__ = ["LegalStrategy"]
