"""通用招呼语模型：为非后端策略提供更中性的首条消息生成。"""

import re
from typing import Any

from src.models.ai_service import AIModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile


class GenericGreetingModel:
    """生成不依赖后端话术的通用招呼语。"""

    GREETING_POSTSCRIPT = (
        "PS: 该招呼语由我编写的求职 Agent 自动发送。"
        "目前正在研发 OpenClaw 求职版，会先基于 LLM 分析岗位 JD，"
        "确认与贵司用人画像基本匹配后再发出。"
        "如收到回复，后续将由我本人真人沟通。"
    )

    def __init__(self, ai_model: AIModel | None = None, domain_label: str = "通用岗位") -> None:
        """初始化通用招呼语模型。"""
        self.client = ai_model or AIModel()
        self.domain_label = domain_label

    def generate_greeting(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        """按当前策略域生成更中性的首条消息。"""
        prompt = self._build_prompt(jd, resume, match_data)
        messages = [
            {
                "role": "system",
                "content": "你擅长将岗位重点和候选人的真实经历压缩成自然、克制、像真人首条消息的中文表达。你不会虚构经历，也不会输出模板化求职话术。",
            },
            {"role": "user", "content": prompt},
        ]
        greeting = self.client.chat(messages, temperature=0.6, max_tokens=512)
        return self._polish_greeting_text(greeting)

    def _build_prompt(self, jd: JobDescription, resume: ResumeProfile, match_data: dict[str, Any]) -> str:
        """构造更通用的招呼语提示词。"""
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
{self.domain_label}

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

    def _polish_greeting_text(self, text: str) -> str:
        """清洗通用招呼语输出。"""
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


__all__ = ["GenericGreetingModel"]
