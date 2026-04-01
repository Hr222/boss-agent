"""后端与AI工程化策略：承接当前项目的主匹配逻辑。"""

from __future__ import annotations

import re
from typing import Any

from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile
from src.models.strategies.candidate_strategy import CandidateStrategy


class BackendAIStrategy(CandidateStrategy):
    """适用于后端、偏全栈、AI 工程化方向的匹配策略。"""

    strategy_id = "backend_ai"
    display_name = "后端与AI工程化"
    GREETING_POSTSCRIPT = (
        "PS: 这条消息是我开发的求职agent自动生成(LLM分析JD→个性化生成→主动发送),"
        "也是我展示自我能力的一部分.后续由本人亲自回复~"
    )

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

    def get_greeting_system_prompt(self) -> str:
        return "你擅长根据岗位真实诉求和候选人的真实经历，写出像真人发出的中文首条沟通消息。你不会虚构，也不会写成模板化求职文案。"

    def build_greeting_prompt(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        resume_text = self.build_resume_text(resume)
        jd_text = self.build_jd_text(jd)
        min_chars = 300
        max_chars = 400
        return f"""你要生成一段用于 Boss 直聘首条沟通的个性化打招呼语。

目标：不要写成求职套话，也不要写成简历摘要；要像真人首条消息一样，先判断岗位真正看重什么，再用真实经历证明我为什么贴合。

推荐风格：
- 更像“深圳宇深灵机”那类写法：岗位判断具体，经历举证完整，语气自然。
- 少写抽象方法论词，少写大而空的判断，优先写真实业务场景、处理动作和为什么能支撑岗位主轴。
- 第二段优先用 1 个完整场景把“问题、处理、结果、和岗位主轴的贴合”串起来，而不是并列堆 2 到 3 个零散亮点。
- 整体语气要像真人聊天里的技术判断，不要像在面试答题，也不要像写评估报告。
- 优先从 JD 描述的业务场景出发来写，而不是围着“匹配不匹配、对齐不对齐”这些词打转。

【岗位信息】
公司：{jd.company_name or '未知'}
岗位：{jd.job_title or '未知'}
城市：{jd.location or '未知'}
链接：{jd.job_url or '无'}

【JD原文】
{jd_text or '无'}

【我的简历】
{resume_text or '无'}

按下面格式输出，严格 4 段，每段 1 句话，不要标题：

第 1 段只写：对岗位核心诉求的判断。
要求：用分析的口吻去讲述, 同时换位思考, 公司应该寻找对应的员工画像. 不要写看描述云云
要求：语气要克制，像读完岗位后的直接判断，不要写得像下定义或下结论报告。

第 2 段只写：我为什么贴合这个岗位。
要求：只拿 1 个最像 JD 场景的真实经历来写，不要并排堆多个案例。
要求：这一段写法尽量简单，顺序就是“当时遇到什么问题，我怎么处理，最后把什么事情做顺了”。
要求：不要讲职责概述，要讲具体问题；也不要讲“匹配、对齐、贴合”，而是让人读完自然感觉到“这种场景你做过”。
要求：要参考JD内容换位思考假如在JD这个场景下, 换算自己能支持力度, 交付能力等

第 3 段只写：我为什么愿意继续深入这个方向。
要求：写我对这种研发方式或工程模式的认可，不要重复第 2 段证据。
要求：这一段控制得短一些，讲清“为什么认可”即可，不要展开成方法论宣言。
要求：不要写成“我非常认可”“我坚定看好”这种过满语气，保持克制。

第 4 段只写：补充亮点或快速补齐能力。
要求：只补 1 个辅助点，收尾自然，不要再展开一串技术名词。
要求：补充点优先选“可迁移到这个岗位的能力”，例如前端联调、设备对接、运维稳定性、AI 工具使用习惯，而不是再讲一遍主轴。
要求: 作为补充可以以在其他方面, 我还会;在意想不到的地方, 我还

额外要求：
- 只输出最终文案，不要解释。
- 总长度尽量在 {min_chars} 到 {max_chars} 字之间。
- 不要写“您好/你好/非常感兴趣/希望有机会/期待沟通”这类求职话术。
- 不要出现项目名、公司名、平台名，不要编造经历或结果。
- 技术术语要克制，重点写“判断”和“证据”，不要写成技能清单。
- 如果岗位重点是 AI 工程化 / Agent / AI Coding，就围绕这些点写；如果重点是全栈交付 / 多端协作 / 设备对接，就围绕交付闭环、联调、稳定性来写。
- 尽量少用“BMad、Context Engineering、新范式、完全一致、完全对齐”这类偏抽象或偏答题感的词。
- 也不要使用“高度一致、直接支撑岗位需求、完全匹配、完全对得上”这类过硬的对齐表达。
- 避免反复出现“这个岗位、岗位要求、核心诉求、主轴、方向”这类词，能少一次就少一次。
- 更像真实沟通，不要像在逐条响应 JD。

输出前自检：
1. 是否严格 4 段。
2. 第 2 段是否有具体问题证据，而不是职责概述。
3. 第 2 段是否回到了 JD 里的具体场景，而不是在抽象地谈“匹配岗位要求”。
4. 第 2 段结尾是否轻轻带回了 JD 里的那类活，而不是停在纯经历描述。
5. 第 1 段是否足够具体，第 3 段是否足够克制，第 4 段是否只是补充而不是重复主轴。
6. 是否像真人消息，而不是简历摘要。

请直接返回最终文案。"""

    def validate_greeting_output(self, text: str) -> tuple[bool, list[str]]:
        issues: list[str] = []
        paragraphs = self.split_paragraphs(text)
        char_count = self.count_visible_chars(text)
        if len(paragraphs) != 4:
            issues.append(f"当前只有 {len(paragraphs)} 段，必须严格为 4 段。")
        if char_count < 300:
            issues.append(f"当前字数为 {char_count}，低于 300。")
        if char_count > 420:
            issues.append(f"当前字数为 {char_count}，超过 420。")
        return not issues, issues

    def rewrite_greeting_with_feedback(
        self,
        ai_model,
        messages: list[dict[str, str]],
        draft: str,
        issues: list[str],
    ) -> str:
        feedback = (
            "你刚才的输出不合格，请严格按要求重写。\n"
            f"问题：{' '.join(issues)}\n"
            "重写要求：\n"
            "1. 严格输出 4 个自然段，每段 1 句话，段落之间必须换行。\n"
            "2. 不要把 4 段合并成 1 段。\n"
            "3. 保持自然聊天口吻，不要加标题，不要解释。\n"
            "4. 保证字数落在允许范围内，不要明显过短或过长。\n"
            "5. 保留原本的岗位判断和经历贴合主轴，但把结构改对。\n"
            f"原输出：\n{draft.strip()}"
        )
        retry_messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": feedback},
        ]
        return ai_model.chat(retry_messages, temperature=self.get_greeting_temperature(), max_tokens=self.get_greeting_max_tokens())

    def finalize_greeting_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        postscript = self.GREETING_POSTSCRIPT.strip()
        if not postscript:
            return cleaned
        return f"{cleaned}\n({postscript})" if cleaned else f"({postscript})"

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
        if any(keyword in title for keyword in ["前端", "react", "vue", "法务", "律师", "合规", "ui", "ux", "设计师", "视觉设计", "交互设计"]):
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
