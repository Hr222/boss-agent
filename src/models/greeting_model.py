"""招呼语模型：负责提示词构造与结果清洗。"""

import re
from typing import Any

from src.models.ai_model import AIModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile


class GreetingModel:
    """封装招呼语生成上下文、提示词和文本清洗逻辑。"""

    GREETING_POSTSCRIPT = (
        "PS: 该招呼语由我编写的求职 Agent 自动发送。"
        "目前正在研发 OpenClaw 求职版，会先基于 LLM 分析岗位 JD，"
        "确认与贵司用人画像基本匹配后再发出。"
        "如收到回复，后续将由我本人真人沟通。"
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

    def __init__(self, ai_model: AIModel | None = None) -> None:
        """初始化招呼语生成器。"""
        self.client = ai_model or AIModel()

    def generate_greeting(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """生成最终招呼语，并在末尾附加固定说明。"""
        greeting_context = self._build_greeting_context(jd, resume, match_data)
        prompt = self._build_greeting_prompt(jd, greeting_context)
        messages = [
            {
                "role": "system",
                "content": "你擅长把岗位职责和候选人的真实证据压缩成一段自然、克制、像真人首条消息的中文表达。你不会虚构经历，也不会输出模板化求职话术。",
            },
            {"role": "user", "content": prompt},
        ]
        greeting = self.client.chat(messages, temperature=0.6, max_tokens=512)
        return self._polish_greeting_text(greeting, greeting_context)

    def _build_greeting_prompt(self, jd: JobDescription, greeting_context: dict[str, Any]) -> str:
        """把 JD 重点和简历证据组织成最终提示词。"""
        selected_cases = [
            case.get("summary", "").strip()
            for case in greeting_context.get("selected_cases", [])
            if case.get("summary")
        ]
        evidence_items = [
            item.get("evidence", "").strip()
            for item in greeting_context.get("responsibility_evidence", [])
            if item.get("evidence")
        ]
        impact_items = [str(item).strip() for item in greeting_context.get("impact_highlights", []) if str(item).strip()]
        extra_strengths = [
            str(item).strip() for item in greeting_context.get("extra_workplace_strengths", []) if str(item).strip()
        ]

        # 这里只保留去重后的事实片段，避免提示词里重复堆叠相同信息。
        resume_facts: list[str] = []
        for item in evidence_items + selected_cases + impact_items + extra_strengths:
            if item and item not in resume_facts:
                resume_facts.append(item)

        return f"""你现在要模拟 Boss 直聘上的首条打招呼消息。

【岗位】
职位: {jd.job_title}
公司: {jd.company_name}
JD重点: {' | '.join(greeting_context.get('jd_requirement_highlights', [])) or '无'}
岗位主职责: {' | '.join(greeting_context.get('primary_responsibilities', [])) or '无'}
JD明确技能: {', '.join(greeting_context.get('strict_jd_skills', [])) or '无'}

【我的技术定位】
{greeting_context.get('skill_positioning', '无')}

【我的真实证据】
职责对应证据: {' | '.join(evidence_items) or '无'}
真实案例: {' | '.join(selected_cases) or '无'}
结果型亮点: {' | '.join(impact_items) or '无'}
可轻带的补充事实: {' | '.join(extra_strengths) or '无'}
可补充提及的技能: {', '.join(greeting_context.get('extra_skills', [])) or '无'}
JD强钩子: {' | '.join(greeting_context.get('jd_anchor_terms', [])) or '无'}
已证实可提的AI/工程化信号: {' | '.join(greeting_context.get('verified_resume_signals', [])) or '无'}

【硬约束】
1. 只写最终打招呼语，不要解释，不要分析，不要分点。
2. 长度控制在 110 到 170 个中文字符之间。
3. 语气像真人发出的第一条消息，不要像简历摘要，不要像自我吹嘘。
4. 不要出现“希望有机会”“期待沟通”“期待交流”“我相信我能胜任”“非常感兴趣”“匹配度很高”。
5. 不要写成已经在对方公司任职的口吻。
6. 直接围绕岗位最核心的 1 到 2 个要求，结合上面的真实经历来写。
7. 优先从 JD强钩子 里只选 1 到 2 个点来回应，不要面面俱到。
8. 只有当量化结果和 JD 主轴直接相关时，才带一个具体结果；否则不要硬塞“30秒压到3秒”这类性能案例。
9. 如果 JD 主轴是 AI Coding、Agent、MCP、Skill、GitHub、Claude Code、Cursor、Workflow、海外模型，就优先回应这些点，不要把数据库优化写成主体。
10. 如果 JD 主轴是 Web 全栈、前端协同、小程序、支付、SDK、硬件对接、多端交付，就优先回应交付闭环、联调、系统落地，不要把纯后端性能优化写成主体。
11. 不能复述 JD 词汇后就结束，必须落到“我实际做过什么”。
12. 不要编造量化、金融、交易系统相关经历；没有就不要硬写。
13. 不要出现公司名、项目名，直接说做过什么、结果怎样、和岗位哪里对得上。
14. 不要用“我有X年经验”“我擅长”“熟悉”“技术栈匹配度很高”这类简历式总结。
15. 不要把 JD 没重点要求的技能写成主体，附加技能最多只在最后轻带一句。
16. 不要把“量化投研平台、交易系统”写成已有经历，只能写成岗位当前场景；正文主体应落在上面有证据的后端、API、数据库、性能优化、稳定性等内容。
17. 不要以“您好”“你好”“看过岗位详情”“看到岗位重点在”这类泛化寒暄开头，直接进入岗位相关工作内容。
18. 不要罗列技能名，优先写具体做过的事、结果和处理过的问题。
19. 正文尽量写成 2 句到 3 句：第一句直接贴岗位主轴，第二句给证据，第三句只在确有必要时补一条相关能力。
20. 可以补 1 个通用能力事实，例如团队推进、接口联调、稳定性交付、代码规范，但只能来自上面的真实证据，而且不能抢主轴。
21. 最后一句不要再做能力判断，应落在真实工作场景，不要写成求职结尾。
22. 下面这些事实可以用，但只能基于原意改写，不能新增经历：{' | '.join(resume_facts) or '无'}
23. 如果候选人的技术定位明确写了“Java是主线，Python已用于实际业务开发”，就不能写成“主要用Python、只接触过Java”这类主次颠倒的话。
24. Python能力如果被提及，应如实表达为“已用于实际业务开发/工程落地”，不要写成一窍不通，也不要写成绝对主力，除非岗位证据明确支持。
25. 严禁附加 PS、括号说明、Agent 自述、真人回复说明。

请直接返回最终文案，不要解释。"""

    def _build_greeting_context(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> dict[str, Any]:
        """抽取生成招呼语时需要的上下文证据。"""
        jd_focus_points = self._extract_jd_focus_points(jd)
        return {
            "jd_focus_points": jd_focus_points,
            "jd_requirement_highlights": self._extract_jd_requirement_highlights(jd),
            "skill_positioning": self._build_skill_positioning(resume),
            "selected_cases": self._select_resume_cases(jd, resume),
            "impact_highlights": self._extract_impact_highlights(resume),
            "extra_workplace_strengths": self._extract_extra_workplace_strengths(resume),
            "matched_skills": list(match_data.get("matched_skills", []) or [])[:6],
            "matched_experience": list(match_data.get("matched_experience", []) or [])[:4],
            "extra_skills": self._extract_extra_skills(jd_focus_points, resume.skills),
            "strict_jd_skills": self._extract_strict_jd_skills(jd),
            "primary_responsibilities": self._extract_primary_responsibilities(jd),
            "responsibility_evidence": self._build_responsibility_evidence(jd, resume),
            "forbidden_main_points": self._extract_forbidden_main_points(jd, resume),
            "jd_anchor_terms": self._extract_jd_anchor_terms(jd),
            "verified_resume_signals": self._extract_verified_resume_signals(resume),
        }

    def _build_skill_positioning(self, resume: ResumeProfile) -> str:
        """根据简历自述提炼技术主次关系，避免模型把画像写反。"""
        source_text = " ".join(
            [
                resume.target_position or "",
                resume.self_introduction or "",
                " ".join(resume.advantages or []),
                " ".join(resume.skills or []),
            ]
        ).lower()

        has_java = "java" in source_text or "spring" in source_text
        has_python = "python" in source_text or "fastapi" in source_text or "django" in source_text

        if has_java and has_python:
            return "Java 是主要开发语言和后端主线，Python 也已用于实际业务开发与 AI 工程化场景，能够独立承担日常后端业务开发。"
        if has_java:
            return "Java 是主要开发语言和后端主线。"
        if has_python:
            return "Python 已用于实际业务开发。"
        return "以后端开发为主。"

    def _extract_jd_focus_points(self, jd: JobDescription) -> list[str]:
        """提取 JD 中最值得聚焦的技能和方向标签。"""
        source_text = " ".join([jd.job_title or "", jd.job_requirements or "", jd.job_description or "", ", ".join(jd.tags or [])])
        normalized_text = self._normalize_text(source_text)
        focus_points: list[str] = []
        for skill in ["Python", "Django", "Flask", "FastAPI", "MySQL", "PostgreSQL", "Redis", "Docker", "Kubernetes", "Linux", "Spring", "Tornado"]:
            patterns = self.LANGUAGE_PATTERNS.get(skill) or self.FRAMEWORK_PATTERNS.get(skill) or [rf"\b{skill.lower()}\b"]
            if self._contains_item(normalized_text, patterns):
                focus_points.append(skill)
        for keyword in ["高并发", "微服务", "分布式", "性能优化", "架构设计", "量化", "交易系统", "数据库优化"]:
            if keyword.lower() in normalized_text:
                focus_points.append(keyword)
        return focus_points[:6]

    def _select_resume_cases(self, jd: JobDescription, resume: ResumeProfile) -> list[dict[str, str]]:
        """从工作/项目经历里选最贴近 JD 的案例。"""
        jd_text = self._normalize_text(" ".join([jd.job_title or "", jd.job_requirements or "", jd.job_description or ""]))
        scored_cases: list[tuple[int, dict[str, str]]] = []
        for work in resume.work_experience:
            content = f"{work.position} {work.description}"
            score = self._score_case_relevance(jd_text, content)
            scored_cases.append((score, {"type": "work", "title": f"{work.company} | {work.position}", "summary": work.description}))
        for project in resume.project_experience:
            content = " ".join([project.role, project.description, ", ".join(project.technologies)])
            score = self._score_case_relevance(jd_text, content)
            scored_cases.append((score + 1, {"type": "project", "title": f"{project.name} | {project.role}", "summary": project.description}))
        scored_cases.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored_cases[:2]]

    def _extract_jd_requirement_highlights(self, jd: JobDescription) -> list[str]:
        """从 JD 文本里挑出适合进入提示词的重点句子。"""
        raw_text = "\n".join([jd.job_title or "", jd.job_requirements or "", jd.job_description or ""])
        fragments = re.split(r"[。\n；;]", raw_text.replace("\r", "\n"))
        highlights: list[tuple[int, str]] = []
        keywords = ["python", "django", "flask", "fastapi", "mysql", "redis", "docker", "kubernetes", "linux", "高并发", "微服务", "架构", "性能", "接口", "系统"]
        for fragment in fragments:
            sentence = re.sub(r"\s+", " ", fragment).strip(" -:：\t")
            if len(sentence) < 8:
                continue
            normalized_sentence = sentence.lower()
            score = sum(2 for keyword in keywords if keyword in normalized_sentence)
            if "负责" in sentence or "要求" in sentence or "熟悉" in sentence or "经验" in sentence:
                score += 1
            if score > 0:
                highlights.append((score, sentence))
        highlights.sort(key=lambda item: item[0], reverse=True)
        unique_sentences: list[str] = []
        for _, sentence in highlights:
            if sentence not in unique_sentences:
                unique_sentences.append(sentence)
            if len(unique_sentences) >= 3:
                break
        return unique_sentences

    def _extract_impact_highlights(self, resume: ResumeProfile) -> list[str]:
        """抽取带量化结果的履历片段。"""
        highlights: list[str] = []
        for work in resume.work_experience:
            text = re.sub(r"\s+", " ", work.description or "").strip()
            if text and any(token in text for token in ["50%", "5人", "性能", "优化", "30秒", "15秒", "3秒", "99.95%"]):
                highlights.append(text)
        for project in resume.project_experience:
            text = re.sub(r"\s+", " ", project.description or "").strip()
            if text and any(token in text for token in ["99.95%", "微服务", "30秒", "15秒", "3秒"]):
                highlights.append(text)
        unique: list[str] = []
        for item in highlights:
            if item not in unique:
                unique.append(item)
        return unique[:3]

    def _extract_extra_workplace_strengths(self, resume: ResumeProfile) -> list[str]:
        """补充可轻带一句的通用工作能力。"""
        strengths: list[str] = []
        for work in resume.work_experience:
            text = re.sub(r"\s+", " ", work.description or "").strip()
            if not text:
                continue
            if "5人团队" in text or "团队" in text:
                strengths.append("带过 5 人团队推进核心项目交付，也持续参与代码规范和研发流程优化")
            if "api" in text.lower() or "接口" in text:
                strengths.append("做过后端 API 设计和多端联调，线上接口稳定性问题也持续跟过")
        if any("开源" in item for item in resume.advantages):
            strengths.append("平时也比较重视代码规范和可维护性，长期会把研发流程和交付质量一起往前推")
        unique: list[str] = []
        for item in strengths:
            if item not in unique:
                unique.append(item)
        return unique[:3]

    def _score_case_relevance(self, jd_text: str, content: str) -> int:
        """粗粒度评估案例与 JD 的相关度。"""
        normalized_content = self._normalize_text(content)
        score = 0
        for keyword in ["python", "django", "flask", "fastapi", "mysql", "redis", "docker", "kubernetes", "linux", "高并发", "微服务", "性能", "架构", "团队"]:
            if keyword in jd_text and keyword in normalized_content:
                score += 2
            elif keyword in normalized_content:
                score += 1
        return score

    def _extract_extra_skills(self, jd_focus_points: list[str], resume_skills: list[str]) -> list[str]:
        """挑出不与 JD 主轴冲突的附加技能。"""
        jd_set = {item.lower() for item in jd_focus_points}
        return [skill for skill in resume_skills if skill.lower() not in jd_set][:4]

    def _extract_strict_jd_skills(self, jd: JobDescription) -> list[str]:
        """抽取 JD 明确点名的技能项。"""
        text = self._normalize_text(" ".join([jd.job_title, jd.job_requirements, jd.job_description]))
        skills: list[str] = []
        for skill in ["Python", "Django", "Flask", "FastAPI", "Tornado", "MySQL", "PostgreSQL", "Redis", "MongoDB", "Linux", "Docker", "Kubernetes"]:
            patterns = self.LANGUAGE_PATTERNS.get(skill) or self.FRAMEWORK_PATTERNS.get(skill) or [rf"\b{skill.lower()}\b"]
            if self._contains_item(text, patterns):
                skills.append(skill)
        return skills[:6]

    def _extract_primary_responsibilities(self, jd: JobDescription) -> list[str]:
        """把 JD 主职责归纳成可用于文案组织的几个方向。"""
        text = self._normalize_text(" ".join([jd.job_title, jd.job_requirements, jd.job_description]))
        mapping = [
            ("后端接口开发", ["后端", "接口", "api", "联调", "模块开发", "代码编写", "功能开发"]),
            ("数据库设计和查询优化", ["mysql", "postgresql", "redis", "数据库", "sql", "缓存", "表结构"]),
            ("性能优化和稳定性", ["高并发", "性能", "稳定性", "响应速度", "监控", "告警", "调优"]),
            ("微服务拆分和交付", ["微服务", "模块/组件", "showcase", "开放与共享", "devops工具链", "上线交付"]),
            ("数据处理和接口接入", ["数据清洗", "加工", "存储", "多源数据", "行情", "基本面", "回测", "执行引擎"]),
            ("代码规范和团队协作", ["团队", "协作", "文档", "规范", "git", "pep8", "分享", "研究员", "交易员"]),
        ]
        responsibilities: list[str] = []
        for label, keywords in mapping:
            if sum(1 for keyword in keywords if keyword in text) >= 1:
                responsibilities.append(label)
        return responsibilities[:3]

    def _extract_jd_anchor_terms(self, jd: JobDescription) -> list[str]:
        """抽取 JD 中最值得直接回应的强钩子词。"""
        text = self._normalize_text(" ".join([jd.job_title, jd.job_requirements, jd.job_description]))
        anchor_groups = [
            ("AI Coding", ["ai coding", "ai-native", "ai native", "智能编码"]),
            ("Agent", ["agent", "智能体"]),
            ("MCP", ["mcp", "model context protocol"]),
            ("Skill", ["skill", "skills"]),
            ("GitHub", ["github"]),
            ("Claude Code", ["claude code"]),
            ("Cursor", ["cursor"]),
            ("Workflow", ["workflow", "工作流"]),
            ("海外模型", ["openai", "anthropic", "gemini", "claude"]),
            ("前后端闭环交付", ["全栈", "前后端", "独立完成", "闭环"]),
            ("小程序/多端", ["小程序", "web", "app", "多端"]),
            ("支付集成", ["stripe", "paypal", "微信支付", "支付宝", "支付系统"]),
            ("SDK/硬件对接", ["sdk", "打印机", "设备", "机器人", "硬件"]),
            ("接口联调", ["接口", "联调", "api"]),
            ("稳定性/运维", ["稳定性", "ci/cd", "运维", "监控", "k8s", "docker"]),
        ]
        anchors: list[str] = []
        for label, keywords in anchor_groups:
            if any(keyword in text for keyword in keywords):
                anchors.append(label)
        return anchors[:6]

    def _extract_verified_resume_signals(self, resume: ResumeProfile) -> list[str]:
        """从简历中抽取确有证据、适合在招呼语轻带的 AI/工程化信号。"""
        source_text = self._normalize_text(
            " ".join(
                [
                    resume.target_position or "",
                    resume.self_introduction or "",
                    " ".join(resume.advantages or []),
                    " ".join(resume.skills or []),
                    " ".join(work.description or "" for work in resume.work_experience),
                    " ".join(project.description or "" for project in resume.project_experience),
                ]
            )
        )
        mapping = [
            ("GitHub 管理代码", ["github"]),
            ("Cursor", ["cursor"]),
            ("Claude Code", ["claude code"]),
            ("Codex", ["codex"]),
            ("GitHub Copilot", ["github copilot", "copilot"]),
            ("Agent 落地", ["agent"]),
            ("RAG", ["rag"]),
            ("MCP", ["mcp"]),
            ("Skill 编写", ["skill"]),
            ("工作流搭建", ["workflow", "工作流"]),
            ("OpenClaw", ["openclaw"]),
            ("Coze", ["coze"]),
            ("K8s 运维", ["k8s", "kubernetes"]),
        ]
        signals: list[str] = []
        for label, keywords in mapping:
            if any(keyword in source_text for keyword in keywords):
                signals.append(label)
        return signals[:8]

    def _build_responsibility_evidence(self, jd: JobDescription, resume: ResumeProfile) -> list[dict[str, str]]:
        """为主要职责补充简历中的对应证据。"""
        responsibilities = self._extract_primary_responsibilities(jd)
        evidence: list[dict[str, str]] = []
        used_evidence: set[str] = set()
        for responsibility in responsibilities:
            matched_case = ""
            if "数据库" in responsibility:
                matched_case = "做过数据库查询与索引优化，曾把全量月比查询从30秒以上压缩到15秒以内，单营业厅查询压缩到3秒以内"
            elif "接口" in responsibility:
                matched_case = "做过后端 API 设计和多端联调，线上接口稳定性问题也持续跟过"
            elif "性能优化" in responsibility:
                matched_case = "做过复杂业务链路的性能优化和稳定性治理，也负责压测、自动化测试和线上问题跟进"
            elif "微服务" in responsibility:
                matched_case = "做过微服务架构下核心模块的全生命周期开发，实践过 DDD 和洋葱架构，也负责过系统可用性优化"
            elif "数据处理" in responsibility:
                matched_case = "长期做数据处理、存储和接口开发，对链路稳定性和处理效率比较敏感"
            elif "代码规范" in responsibility or "团队协作" in responsibility:
                matched_case = "带过小团队推进项目交付，也持续参与代码规范和研发流程优化"
            if matched_case and matched_case not in used_evidence:
                evidence.append({"responsibility": responsibility, "evidence": matched_case})
                used_evidence.add(matched_case)
        return evidence[:2]

    def _extract_forbidden_main_points(self, jd: JobDescription, resume: ResumeProfile) -> list[str]:
        """识别不应在正文主体展开的技能点。"""
        text = self._normalize_text(" ".join([jd.job_title, jd.job_requirements, jd.job_description]))
        candidates = ["Docker", "Kubernetes", "MongoDB", "RabbitMQ", "Elasticsearch", "AWS", "FastAPI", "Flask", "Django"]
        forbidden: list[str] = []
        for skill in candidates:
            patterns = self.LANGUAGE_PATTERNS.get(skill) or self.FRAMEWORK_PATTERNS.get(skill) or [rf"\b{skill.lower()}\b"]
            if skill in resume.skills and not self._contains_item(text, patterns):
                forbidden.append(skill)
        return forbidden[:4]

    def _polish_greeting_text(self, text: str, greeting_context: dict[str, Any] | None = None) -> str:
        """清洗模型输出，去掉套话并压回真人首条消息风格。"""
        greeting_context = greeting_context or {}
        cleaned = re.sub(r"\s+", " ", (text or "")).strip()
        replacements = [
            (r"^(您好[，,]?\s*|你好[，,]?\s*|嗨[，,]?\s*)", ""),
            (r"^(博彦科技的|华为的|华为技术有限公司的|某大型计算机软件公司的|深圳市星磐信息咨询的)", ""),
            (r"(岗位挺吸引我[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(我很感兴趣[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(经验丰富[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(驾轻就熟[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(希望有机会[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(期待[^。！？!?.]*交流[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(期待[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(非常感兴趣[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(相信我能胜任[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(我相信[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(能够为贵公司[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(为贵公司的[^。！？!?.]*[。！？!?.]?)", ""),
            (r"(在[^，。]{1,20}公司[^，。]*岗位上[^。！？!?.]*[，,]?)", ""),
            (r"(在[^，。]{1,20}(技术有限公司|科技有限公司|有限公司)[^。！？!?.]*[，,]?)", ""),
            (r"^在[^，。]{0,30}岗位上[，,]?", ""),
            (r"^在[^，。]{0,30}公司[^，。]{0,20}[，,]?", ""),
            (r"(知名互联网公司|另一知名公司)", ""),
            (r"\(?PS[:：][^)]*\)?", ""),
            (r"（?该招呼语由我制作的求职agent[^）]*）?", ""),
            (r"（?后续将由我本人真人回复[^）]*）?", ""),
            (r"（?也是本人能力展示的一部分[^）]*）?", ""),
            (r"（?期待您的回复[^）]*）?", ""),
        ]
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned)
        cleaned = cleaned.strip(" ，,。")
        cleaned = cleaned.replace("主要用 Python 和 Django，也接触过 Java 生态", "Java 是主线开发语言，Python 也已经用于实际业务开发，Django 和 FastAPI 都有落地")
        cleaned = cleaned.replace("主要用Python和Django，也接触过Java生态", "Java 是主线开发语言，Python 也已经用于实际业务开发，Django 和 FastAPI 都有落地")
        cleaned = cleaned.replace("Python已用于实际业务开发与AI工程化落地", "Python 也已经用于实际业务开发与 AI 工程化落地，日常后端业务开发没有问题")
        cleaned = cleaned.replace("Python 已用于实际业务开发与AI工程化落地", "Python 也已经用于实际业务开发与 AI 工程化落地，日常后端业务开发没有问题")
        cleaned = cleaned.replace("Python已用于实际业务开发与 AI 工程化落地", "Python 也已经用于实际业务开发与 AI 工程化落地，日常后端业务开发没有问题")
        cleaned = cleaned.replace("Python 已用于实际业务开发与 AI 工程化落地", "Python 也已经用于实际业务开发与 AI 工程化落地，日常后端业务开发没有问题")
        cleaned = cleaned.replace("接口和查询链路支撑过百万级用户访问", "做过数据库查询与链路优化，能够支撑复杂业务场景稳定运行")
        cleaned = cleaned.replace("请求量到过每秒 10 万+", "处理过复杂业务链路的性能优化问题")
        # 如果模型又回到了“简历式开头”，这里再做一次压缩重写。
        banned_openings = ["在过去的五年里", "在过去的五年中", "我有5年Python后端开发经验", "我专注于Python后端开发"]
        if any(cleaned.startswith(prefix) for prefix in banned_openings):
            jd_points = greeting_context.get("jd_focus_points", [])[:2]
            case = (greeting_context.get("selected_cases", []) or [{}])[0]
            prefix = "、".join(jd_points) if jd_points else "后端系统、性能优化"
            summary = re.sub(r"\s+", "", str(case.get("summary", "") or "").strip())
            if len(summary) > 56:
                summary = summary[:56]
            cleaned = f"{prefix}这类事情我一直做得比较多，{summary}".strip(" ，,。")
        sentence_parts = [item.strip() for item in re.split(r"[。！？]", cleaned) if item.strip()]
        if len(sentence_parts) > 3:
            cleaned = "。".join(sentence_parts[:3])
        if len(cleaned) > 185:
            cleaned = cleaned[:185].rstrip("，,、 ")
        if cleaned and cleaned[-1] not in "。！？":
            cleaned += "。"
        postscript = self.GREETING_POSTSCRIPT.strip()
        return cleaned if not postscript else f"{cleaned}\n({postscript})"

    def _normalize_text(self, text: str) -> str:
        """统一做小写和空白压缩，方便后续规则匹配。"""
        return re.sub(r"\s+", " ", (text or "").lower()).strip()

    def _contains_item(self, text: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)


__all__ = ["GreetingModel"]
