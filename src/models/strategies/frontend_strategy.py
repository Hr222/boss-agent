"""前端工程化策略：按中国主流前端技术栈做第一版匹配优化。"""

from __future__ import annotations

import re
from typing import Any

from src.models.ai_model import AIModel
from src.models.generic_greeting_model import GenericGreetingModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class FrontendStrategy(CandidateStrategy):
    """前端工程化方向策略，主轴聚焦 ES6+、TypeScript 与 Vue 生态。"""

    strategy_id = "frontend"
    display_name = "前端工程化"

    # 第一层：主流核心技术，优先用于“是否属于前端方向”的判断。
    CORE_SKILL_PATTERNS = {
        "ES6+": [r"\bes6\b", r"\bes6\+\b", r"es6\+", r"es2015", r"现代js", r"现代javascript"],
        "JavaScript": [r"\bjavascript\b", r"\bjs\b"],
        "TypeScript": [r"\btypescript\b", r"\bts\b"],
        "Vue": [r"\bvue\b", r"vue\.js", r"vue2", r"vue3", r"composition api", r"组合式api"],
        "HTML/CSS": [r"\bhtml\b", r"\bcss\b", r"页面还原", r"响应式布局", r"样式开发"],
    }

    # 第二层：Vue 工程化生态，是国内业务前端更常见的能力组合。
    VUE_ECOSYSTEM_PATTERNS = {
        "Vue Router": [r"vue router", r"\brouter\b", r"前端路由"],
        "Pinia/Vuex": [r"\bpinia\b", r"\bvuex\b", r"状态管理"],
        "Element UI/Plus": [r"element ui", r"element plus", r"ant design vue", r"组件库"],
        "Axios": [r"\baxios\b", r"接口封装", r"请求封装"],
        "Vite/Webpack": [r"\bvite\b", r"\bwebpack\b", r"前端构建", r"工程化构建"],
        "ECharts": [r"\becharts\b", r"数据可视化", r"图表开发"],
        "UniApp/小程序": [r"uni-?app", r"小程序", r"移动端", r"h5"],
    }

    # 第三层：工作方式与交付能力，用于给匹配和招呼语补充上下文。
    DELIVERY_PATTERNS = {
        "组件化开发": [r"组件化", r"组件封装", r"公共组件"],
        "性能优化": [r"性能优化", r"首屏优化", r"懒加载", r"打包优化", r"渲染优化"],
        "兼容与适配": [r"兼容", r"浏览器兼容", r"移动端适配", r"响应式"],
        "联调协作": [r"接口联调", r"前后端联调", r"跨端协作"],
        "工程规范": [r"eslint", r"prettier", r"代码规范", r"git flow", r"工程规范"],
        "AI辅助研发": [r"ai coding", r"ai编程", r"智能编码", r"prompt engineering", r"agent", r"langchain"],
    }

    # 这些职位词一旦在 JD 标题或正文里明显出现，说明当前岗位更像前端方向。
    FRONTEND_ROLE_KEYWORDS = [
        "前端",
        "web前端",
        "h5",
        "vue",
        "react",
        "小程序",
        "可视化",
        "大屏",
    ]

    # 这些岗位词若明显出现，则说明岗位主体更偏其他方向。
    NON_FRONTEND_ROLE_KEYWORDS = [
        "后端",
        "java",
        "python",
        "golang",
        "go",
        "法务",
        "律师",
        "运维",
        "测试",
        "算法",
    ]

    FRONTEND_PATTERNS = {
        **CORE_SKILL_PATTERNS,
        **VUE_ECOSYSTEM_PATTERNS,
        **DELIVERY_PATTERNS,
    }

    def build_rule_precheck(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        jd_text: str,
        resume_text: str,
    ) -> dict[str, Any]:
        """构建前端方向的规则预筛，重点考察 ES6+ / TS / Vue 及工程化能力。"""
        normalized_jd = self._normalize_text(jd_text)
        normalized_resume = self._normalize_text(resume_text)

        # 核心技能用于判断岗位主轴，生态技能用于补充策略上下文。
        required_core_skills = self._extract_required_items(normalized_jd, self.CORE_SKILL_PATTERNS)
        matched_core_skills = [
            item for item in required_core_skills if self._contains_item(normalized_resume, self.CORE_SKILL_PATTERNS[item])
        ]
        missing_core_skills = [item for item in required_core_skills if item not in matched_core_skills]

        required_ecosystem_skills = self._extract_required_items(normalized_jd, self.VUE_ECOSYSTEM_PATTERNS)
        matched_ecosystem_skills = [
            item
            for item in required_ecosystem_skills
            if self._contains_item(normalized_resume, self.VUE_ECOSYSTEM_PATTERNS[item])
        ]
        missing_ecosystem_skills = [item for item in required_ecosystem_skills if item not in matched_ecosystem_skills]

        matched_delivery_items = [
            item for item, patterns in self.DELIVERY_PATTERNS.items() if self._contains_item(normalized_resume, patterns)
        ]
        resume_years = self._parse_years(resume.years_of_experience)
        required_years = self._extract_required_years(normalized_jd)
        hard_gaps: list[str] = []

        # 核心能力缺口用更强约束，生态缺口只轻度压分。
        strong_required_skills = [
            skill for skill in required_core_skills if skill in {"ES6+", "JavaScript", "TypeScript", "Vue", "HTML/CSS"}
        ]
        strong_missing_skills = [skill for skill in strong_required_skills if skill in missing_core_skills]
        if strong_missing_skills:
            hard_gaps.append(f"缺少关键前端能力: {', '.join(strong_missing_skills)}")
        if required_years > resume_years:
            hard_gaps.append(f"年限不足: JD要求约{required_years}年，简历为{resume_years}年")
        if self._is_non_frontend_primary_role(normalized_jd):
            hard_gaps.append("岗位主体并非前端工程化方向")

        cap_score = 100
        if len(hard_gaps) >= 2:
            cap_score = min(cap_score, 65)
        elif hard_gaps:
            cap_score = min(cap_score, 72)
        elif missing_ecosystem_skills:
            cap_score = min(cap_score, 85 if resume_years >= 5 else 80)

        matched_skills = matched_core_skills + [item for item in matched_ecosystem_skills if item not in matched_core_skills]
        missing_skills = strong_missing_skills + [item for item in missing_ecosystem_skills if item not in strong_missing_skills]
        return {
            "required_core_skills": required_core_skills,
            "matched_core_skills": matched_core_skills,
            "missing_core_skills": missing_core_skills,
            "required_ecosystem_skills": required_ecosystem_skills,
            "matched_ecosystem_skills": matched_ecosystem_skills,
            "missing_ecosystem_skills": missing_ecosystem_skills,
            "matched_delivery_items": matched_delivery_items,
            "required_skills": strong_required_skills + [item for item in required_ecosystem_skills if item not in strong_required_skills],
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
        """用前端策略规则兜底 LLM 输出，并补充前端语义化分析。"""
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

        # 对前端方向，补充真实能支撑文案生成的匹配亮点，避免只剩技能罗列。
        matched_experience = list(result.get("matched_experience", []) or [])
        for item in precheck.get("matched_delivery_items", []):
            if item not in matched_experience:
                matched_experience.append(item)
        result["matched_experience"] = matched_experience[:6]

        advantages = list(result.get("advantages", []) or [])
        frontend_advantages = []
        if precheck.get("matched_core_skills"):
            frontend_advantages.append(f"前端主轴能力覆盖：{', '.join(precheck['matched_core_skills'])}")
        if precheck.get("matched_ecosystem_skills"):
            frontend_advantages.append(f"Vue 工程化能力覆盖：{', '.join(precheck['matched_ecosystem_skills'])}")
        if precheck.get("matched_delivery_items"):
            frontend_advantages.append(f"交付能力可支撑：{', '.join(precheck['matched_delivery_items'])}")
        for item in frontend_advantages:
            if item not in advantages:
                advantages.append(item)
        result["advantages"] = advantages[:5]

        if precheck["hard_gaps"]:
            analysis = (result.get("analysis", "") or "").strip()
            gap_text = "；".join(precheck["hard_gaps"])
            if gap_text not in analysis:
                result["analysis"] = f"{analysis} 规则预筛提示：{gap_text}。".strip()
        return result

    def generate_greeting(
        self,
        ai_model: AIModel,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """前端方向使用更贴近 ES6+ / TS / Vue 生态的通用招呼语模型。"""
        return GenericGreetingModel(
            ai_model,
            domain_label="前端工程化（ES6+ / TypeScript / Vue）",
        ).generate_greeting(jd, resume, match_data)

    def infer_from_resume(self, resume: ResumeProfile) -> bool:
        """按前端关键词粗判是否适合。"""
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
                "前端",
                "vue",
                "typescript",
                "javascript",
                "html",
                "css",
                "es6",
                "vite",
                "pinia",
                "vuex",
                "element",
                "ai coding",
                "ai编程",
            ]
        )

    def _extract_required_items(self, text: str, pattern_map: dict[str, list[str]]) -> list[str]:
        """从 JD 文本中提取当前 pattern_map 定义的技能项。"""
        return [item for item, patterns in pattern_map.items() if self._contains_item(text, patterns)]

    def _contains_item(self, text: str, patterns: list[str]) -> bool:
        """统一做正则匹配，避免重复写 flags。"""
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _extract_required_years(self, text: str) -> int:
        """提取 JD 年限要求。"""
        match = re.search(r"(\d+)\s*年", text)
        return int(match.group(1)) if match else 0

    def _parse_years(self, value: str) -> int:
        """把简历工龄文本转换成整数。"""
        match = re.search(r"(\d+)", value or "")
        return int(match.group(1)) if match else 0

    def _normalize_text(self, text: str) -> str:
        """统一做空白压缩和小写处理。"""
        return re.sub(r"\s+", " ", (text or "").lower()).strip()

    def _is_non_frontend_primary_role(self, normalized_jd: str) -> bool:
        """判断 JD 主体是否明显偏离前端方向。"""
        if any(keyword in normalized_jd for keyword in self.FRONTEND_ROLE_KEYWORDS):
            return False
        if any(keyword in normalized_jd for keyword in self.NON_FRONTEND_ROLE_KEYWORDS):
            return True
        return False


__all__ = ["FrontendStrategy"]
