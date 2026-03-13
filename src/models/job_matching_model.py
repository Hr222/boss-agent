"""岗位匹配模型：负责根据策略执行 LLM 匹配与规则兜底。"""

import json
import re
from typing import Any, Optional

from src.models.ai_model import AIModel
from src.models.job_description import JobDescription
from src.models.job_match_result import JobMatchResult
from src.models.resume_profile import ResumeProfile
from src.models.resume_store import ResumeStore
from src.models.strategies.strategy_factory import StrategyFactory


class JobMatchingModel:
    """按当前策略分析 JD 与简历的匹配度，并生成对应招呼语。"""

    def __init__(
        self,
        ai_model: Optional[AIModel] = None,
        strategy_id: str = "backend_ai",
    ) -> None:
        """初始化 AI 客户端、简历仓储与当前策略。"""
        self.client = ai_model or AIModel()
        self.resume_store = ResumeStore()
        self.strategy_id = strategy_id
        self.strategy = StrategyFactory.create(strategy_id if strategy_id != "auto" else "backend_ai")

    def set_strategy(self, strategy_id: str, resume: ResumeProfile | None = None) -> None:
        """切换当前匹配策略。"""
        self.strategy_id = strategy_id
        if strategy_id == "auto":
            self.strategy = StrategyFactory.create_auto(resume)
        else:
            self.strategy = StrategyFactory.create(strategy_id)

    def analyze_match(self, jd: JobDescription, resume: Optional[ResumeProfile] = None) -> Optional[JobMatchResult]:
        """执行完整匹配流程：读取简历、规则预筛、LLM 分析、招呼语生成。"""
        resume = resume or self.resume_store.load_resume()
        if not resume:
            print("错误: 未找到简历，请先创建简历")
            return None
        if self.strategy_id == "auto":
            self.strategy = StrategyFactory.create_auto(resume)

        jd_text = self._build_jd_text(jd)
        resume_text = self.resume_store.get_resume_text(resume)
        print(f"正在分析职位匹配[{self.strategy.display_name}]: {jd.job_title} @ {jd.company_name}")
        precheck = self.strategy.build_rule_precheck(jd, resume, jd_text, resume_text)

        try:
            analysis_result = self.client.analyze_jd_match(jd_text, resume_text, precheck)
            match_data = self._parse_match_json(analysis_result)
            match_data = self.strategy.apply_rule_postcheck(match_data, precheck, jd)
            greeting = self.strategy.generate_greeting(self.client, jd, resume, match_data)
            return JobMatchResult(
                job_id=jd.job_id,
                job_title=jd.job_title,
                company_name=jd.company_name,
                match_score=match_data.get("match_score", 0),
                match_level=match_data.get("match_level", "中"),
                matched_skills=match_data.get("matched_skills", []),
                missing_skills=match_data.get("missing_skills", []),
                matched_experience=match_data.get("matched_experience", []),
                advantages=match_data.get("advantages", []),
                analysis=match_data.get("analysis", ""),
                suggestions=match_data.get("suggestions", []),
                greeting_message=greeting,
                is_recommended=match_data.get("is_recommended", False),
            )
        except json.JSONDecodeError as error:
            print(f"解析LLM返回结果失败: {error}")
            print(f"原始返回: {analysis_result}")
            return None
        except Exception as error:
            print(f"匹配分析失败: {error}")
            return None

    def _build_jd_text(self, jd: JobDescription) -> str:
        """把 JD 结构化字段拼成统一的 LLM 输入文本。"""
        lines = [
            f"职位名称: {jd.job_title}",
            f"公司名称: {jd.company_name}",
            f"薪资范围: {jd.salary_range}",
            f"工作地点: {jd.location}",
            "",
            "职位要求:",
            jd.job_requirements,
            "",
            "职位描述:",
            jd.job_description,
        ]
        if jd.tags:
            lines.extend(["", "技能标签:", ", ".join(jd.tags)])
        return "\n".join(lines)

    def _parse_match_json(self, raw_text: str) -> dict[str, Any]:
        """兼容解析纯 JSON 和 ```json 代码块。"""
        text = (raw_text or "").strip()
        if not text:
            raise json.JSONDecodeError("empty response", text, 0)
        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fenced_match:
            return json.loads(fenced_match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            return json.loads(candidate)
        return json.loads(text)

    def print_match_result(self, result: JobMatchResult) -> None:
        """控制台调试输出，便于人工查看单次分析结果。"""
        print("\n" + "=" * 60)
        print(f"📊 匹配分析结果: {result.job_title} @ {result.company_name}")
        print("=" * 60)
        score_color = self._get_score_color(result.match_score)
        print(f"\n🎯 匹配度: {score_color}{result.match_score:.1f}分\033[0m ({result.match_level})")
        print("✅ 推荐投递" if result.is_recommended else "⚠️  谨慎考虑")
        if result.matched_skills:
            print(f"\n✓ 匹配技能: {', '.join(result.matched_skills)}")
        if result.missing_skills:
            print(f"\n✗ 缺失技能: {', '.join(result.missing_skills)}")
        if result.matched_experience:
            print("\n📝 匹配经验:")
            for exp in result.matched_experience:
                print(f"  • {exp}")
        if result.advantages:
            print("\n⭐ 个人优势:")
            for adv in result.advantages:
                print(f"  • {adv}")
        print("\n📋 详细分析:")
        print(f"  {result.analysis}")
        if result.suggestions:
            print("\n💡 建议:")
            for sug in result.suggestions:
                print(f"  • {sug}")
        print("\n💬 定制化打招呼语:")
        print("-" * 60)
        print(result.greeting_message)
        print("-" * 60)

    def _get_score_color(self, score: float) -> str:
        """按分数返回控制台颜色代码。"""
        if score >= 80:
            return "\033[92m"
        if score >= 60:
            return "\033[93m"
        return "\033[91m"


__all__ = ["JobMatchingModel"]
