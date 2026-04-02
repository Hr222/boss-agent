"""UI 设计策略：覆盖界面、视觉与交互设计方向的基础预筛规则。"""

from __future__ import annotations

import re
from typing import Any

from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class UIDesignStrategy(CandidateStrategy):
    """UI 设计方向策略，主轴聚焦视觉表达、设计工具与交互协作。"""

    strategy_id = "ui_design"
    display_name = "UI设计"
    GREETING_POSTSCRIPT = (
        "PS: 该招呼语由我编写的求职 Agent 自动发送。"
        "目前正在研发 OpenClaw 求职版，会先基于 LLM 分析岗位 JD，"
        "确认与贵司用人画像基本匹配后再发出。"
        "如收到回复，后续将由我本人真人沟通。"
    )

    CORE_SKILL_PATTERNS = {
        "UI设计": [r"\bui\b", r"ui设计", r"界面设计", r"视觉设计", r"客户端界面"],
        "UX/交互": [r"\bux\b", r"交互设计", r"用户体验", r"信息架构", r"交互稿"],
        "Figma": [r"\bfigma\b"],
        "Sketch": [r"\bsketch\b"],
        "Adobe XD": [r"adobe xd", r"\bxd\b"],
        "Photoshop": [r"\bphotoshop\b", r"\bps\b"],
    }

    VISUAL_PATTERNS = {
        "设计系统": [r"设计系统", r"design system", r"组件规范", r"样式规范", r"视觉规范"],
        "高保真": [r"高保真", r"高保真原型", r"高保真稿"],
        "原型设计": [r"原型", r"线框图", r"交互原型", r"流程图"],
        "动效表达": [r"动效", r"交互动效", r"motion", r"动画设计"],
        "多端适配": [r"多端", r"响应式", r"移动端", r"pc端", r"适配"],
        "品牌视觉": [r"品牌视觉", r"视觉升级", r"品牌规范", r"运营设计"],
    }

    COLLABORATION_PATTERNS = {
        "需求分析": [r"需求分析", r"业务理解", r"场景梳理"],
        "开发协作": [r"开发协作", r"设计走查", r"前后端联调", r"与开发对接"],
        "用户研究": [r"用户研究", r"可用性测试", r"用户访谈", r"竞品分析"],
        "AI辅助设计": [r"ai设计", r"ai绘图", r"ai辅助设计", r"midjourney", r"stable diffusion"],
    }

    UI_ROLE_KEYWORDS = [
        "ui",
        "ux",
        "ui设计",
        "视觉设计",
        "界面设计",
        "交互设计",
        "产品设计师",
        "设计师",
        "用户体验",
    ]

    NON_UI_ROLE_KEYWORDS = [
        "后端",
        "java",
        "python",
        "golang",
        "前端开发",
        "法务",
        "律师",
        "测试",
        "运维",
        "算法",
    ]

    UI_PATTERNS = {
        **CORE_SKILL_PATTERNS,
        **VISUAL_PATTERNS,
        **COLLABORATION_PATTERNS,
    }

    def build_rule_precheck(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        jd_text: str,
        resume_text: str,
    ) -> dict[str, Any]:
        """构建 UI 设计方向的规则预筛。"""
        normalized_jd = self._normalize_text(jd_text)
        normalized_resume = self._normalize_text(resume_text)

        required_core_skills = self._extract_required_items(normalized_jd, self.CORE_SKILL_PATTERNS)
        matched_core_skills = [
            item for item in required_core_skills if self._contains_item(normalized_resume, self.CORE_SKILL_PATTERNS[item])
        ]
        missing_core_skills = [item for item in required_core_skills if item not in matched_core_skills]

        required_visual_skills = self._extract_required_items(normalized_jd, self.VISUAL_PATTERNS)
        matched_visual_skills = [
            item
            for item in required_visual_skills
            if self._contains_item(normalized_resume, self.VISUAL_PATTERNS[item])
        ]
        missing_visual_skills = [item for item in required_visual_skills if item not in matched_visual_skills]

        matched_collaboration_items = [
            item for item, patterns in self.COLLABORATION_PATTERNS.items() if self._contains_item(normalized_resume, patterns)
        ]
        required_years = self._extract_required_years(normalized_jd)
        resume_years = self._parse_years(resume.years_of_experience)
        hard_gaps: list[str] = []

        strong_required_skills = [skill for skill in required_core_skills if skill in {"UI设计", "UX/交互", "Figma", "Sketch"}]
        strong_missing_skills = [skill for skill in strong_required_skills if skill in missing_core_skills]
        if strong_missing_skills:
            hard_gaps.append(f"缺少关键设计能力: {', '.join(strong_missing_skills)}")
        if required_years > resume_years:
            hard_gaps.append(f"年限不足: JD要求约{required_years}年，简历为{resume_years}年")
        if self._is_non_ui_primary_role(normalized_jd):
            hard_gaps.append("岗位主体并非UI设计方向")

        cap_score = 100
        if len(hard_gaps) >= 2:
            cap_score = min(cap_score, 65)
        elif hard_gaps:
            cap_score = min(cap_score, 72)
        elif missing_visual_skills:
            cap_score = min(cap_score, 85 if resume_years >= 5 else 80)

        matched_skills = matched_core_skills + [item for item in matched_visual_skills if item not in matched_core_skills]
        missing_skills = strong_missing_skills + [item for item in missing_visual_skills if item not in strong_missing_skills]
        return {
            "required_core_skills": required_core_skills,
            "matched_core_skills": matched_core_skills,
            "missing_core_skills": missing_core_skills,
            "required_visual_skills": required_visual_skills,
            "matched_visual_skills": matched_visual_skills,
            "missing_visual_skills": missing_visual_skills,
            "matched_collaboration_items": matched_collaboration_items,
            "required_skills": strong_required_skills + [item for item in required_visual_skills if item not in strong_required_skills],
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "required_years": required_years,
            "resume_years": resume_years,
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
        """用 UI 设计策略规则兜底 LLM 输出。"""
        result = dict(match_data)
        score = min(float(result.get("match_score", 0) or 0), float(precheck["cap_score"]))
        result["match_score"] = score
        result["match_level"] = "高" if score >= 80 else "中" if score >= 60 else "低"

        missing_skills = list(result.get("missing_skills", []) or [])
        for skill in precheck["missing_skills"]:
            if skill not in missing_skills:
                missing_skills.append(skill)
        result["missing_skills"] = missing_skills[:8]
        if precheck["must_not_recommend"] or score < 75:
            result["is_recommended"] = False

        matched_experience = list(result.get("matched_experience", []) or [])
        for item in precheck.get("matched_collaboration_items", []):
            if item not in matched_experience:
                matched_experience.append(item)
        result["matched_experience"] = matched_experience[:6]

        advantages = list(result.get("advantages", []) or [])
        ui_advantages = []
        if precheck.get("matched_core_skills"):
            ui_advantages.append(f"设计主轴能力覆盖：{', '.join(precheck['matched_core_skills'])}")
        if precheck.get("matched_visual_skills"):
            ui_advantages.append(f"视觉与交互能力覆盖：{', '.join(precheck['matched_visual_skills'])}")
        if precheck.get("matched_collaboration_items"):
            ui_advantages.append(f"跨团队协作可支撑：{', '.join(precheck['matched_collaboration_items'])}")
        for item in ui_advantages:
            if item not in advantages:
                advantages.append(item)
        result["advantages"] = advantages[:5]

        if precheck["hard_gaps"]:
            analysis = (result.get("analysis", "") or "").strip()
            gap_text = "；".join(precheck["hard_gaps"])
            if gap_text not in analysis:
                result["analysis"] = f"{analysis} 规则预筛提示：{gap_text}。".strip()
        return result

    def get_greeting_system_prompt(self) -> str:
        return "你擅长根据 UI 设计岗位的真实工作内容和候选人的真实经历，写出自然、克制、像真人首条消息的中文表达。你不会虚构经历，也不会写成模板化求职话术。"

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

【写作目标】
1. 只输出最终打招呼语，不要解释，不要分点。
2. 长度控制在 140 到 220 个中文字符之间。
3. 语气像真人发出的第一条消息，不能像简历总结。
4. 只能基于上面的真实信息，不要虚构经历和量化结果。
5. 不要写“希望有机会”“期待沟通”“非常感兴趣”“我相信我能胜任”。
6. 直接围绕岗位最核心的 1 到 2 个要求来写，优先写界面、交互、设计系统、走查协作、多端适配这些真实工作内容。
7. 不要出现公司名、项目名、模板化寒暄。
8. 不要面面俱到，不要把所有匹配点都写进去。
9. 优先写做过的设计场景、协作方式和交付结果，不要罗列工具名。
10. 最后一句自然落在设计协作、体验判断或快速补位能力上，不要写求职总结。
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
        if len(cleaned) > 220:
            cleaned = cleaned[:220].rstrip("，,、 ")
        if cleaned and cleaned[-1] not in "。！？":
            cleaned += "。"
        postscript = self.GREETING_POSTSCRIPT.strip()
        return cleaned if not postscript else f"{cleaned}\n({postscript})"

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """按 UI 设计关键词粗判是否适合。"""
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
        return any(
            keyword in text
            for keyword in [
                "ui",
                "ux",
                "界面设计",
                "视觉设计",
                "交互设计",
                "figma",
                "sketch",
                "adobe xd",
                "photoshop",
                "设计系统",
                "用户体验",
            ]
        )

    def _extract_required_items(self, text: str, pattern_map: dict[str, list[str]]) -> list[str]:
        return [item for item, patterns in pattern_map.items() if self._contains_item(text, patterns)]

    def _contains_item(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _extract_required_years(self, text: str) -> int:
        match = re.search(r"(\d+)\s*年", text)
        return int(match.group(1)) if match else 0

    def _parse_years(self, value: str) -> int:
        match = re.search(r"(\d+)", value or "")
        return int(match.group(1)) if match else 0

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").lower()).strip()

    def _is_non_ui_primary_role(self, normalized_jd: str) -> bool:
        if any(keyword in normalized_jd for keyword in self.UI_ROLE_KEYWORDS):
            return False
        if any(keyword in normalized_jd for keyword in self.NON_UI_ROLE_KEYWORDS):
            return True
        return False


__all__ = ["UIDesignStrategy"]
