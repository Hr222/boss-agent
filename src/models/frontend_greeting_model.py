"""Frontend-specific greeting model using the same 4-paragraph structure."""

from __future__ import annotations

import re
from typing import Any

from src.models.ai_model import AIModel
from src.models.job_description import JobDescription
from src.models.resume_profile import ResumeProfile


class FrontendGreetingModel:
    """Generate frontend-oriented greetings with the validated 4-paragraph structure."""

    GREETING_POSTSCRIPT = (
        "P.S. 这条消息是我开发的求职agent自动生成(LLM分析JD→个性化生成→主动发送),"
        "也是我展示自我能力的一部分.后续由本人亲自回复~"
    )

    def __init__(self, ai_model: AIModel | None = None) -> None:
        self.client = ai_model or AIModel()

    def generate_greeting(
        self,
        jd: JobDescription,
        resume: ResumeProfile,
        match_data: dict[str, Any],
    ) -> str:
        prompt = self._build_prompt(jd, resume, match_data)
        messages = [
            {
                "role": "system",
                "content": "你擅长根据前端岗位的真实场景和候选人的真实经历，写出像真人发出的中文首条沟通消息。你不会虚构，也不会写成模板化求职文案。",
            },
            {"role": "user", "content": prompt},
        ]
        result = self.client.chat(messages, temperature=0.6, max_tokens=800)
        is_valid, issues = self._validate_output(result)
        if not is_valid:
            result = self._rewrite_with_feedback(messages, result, issues)
        return self._append_postscript(result)

    def _build_prompt(self, jd: JobDescription, resume: ResumeProfile, match_data: dict[str, Any]) -> str:
        resume_text = self._build_resume_text(resume)
        jd_text = self._build_jd_text(jd)
        matched_skills = ", ".join(match_data.get("matched_skills", []) or []) or "无"
        matched_experience = " | ".join(match_data.get("matched_experience", []) or []) or "无"
        advantages = " | ".join(match_data.get("advantages", []) or []) or "无"
        return f"""你要生成一段用于 Boss 直聘首条沟通的个性化打招呼语。

目标：不要写成求职套话，也不要写成简历摘要；要像真人首条消息一样，先判断这个前端岗位真正看重什么，再用真实经历证明我为什么能接住这类交付。

推荐风格：
- 岗位判断具体，经历举证完整，语气自然。
- 优先写前端场景里的真实问题，比如页面交付、组件封装、前后端联调、性能优化、兼容适配、多端协作、工程规范，而不是泛泛谈技术热情。
- 第二段优先用 1 个完整场景把“问题、处理、结果、以及放到这个岗位里怎么用得上”串起来。
- 整体语气要像真人聊天里的技术判断，不要像在答题，也不要像写简历总结。

【岗位信息】
公司：{jd.company_name or '未知'}
岗位：{jd.job_title or '未知'}
城市：{jd.location or '未知'}
链接：{jd.job_url or '无'}

【JD原文】
{jd_text or '无'}

【我的简历】
{resume_text or '无'}

【已有匹配线索】
匹配技能：{matched_skills}
匹配经历：{matched_experience}
优势：{advantages}

按下面格式输出，严格 4 段，每段 1 句话，不要标题：

第 1 段只写：对岗位核心诉求的判断。
要求：用分析口吻讲清楚公司更想找哪类前端画像，例如能独立交付页面和联调的人、能处理多端/小程序的人、能做组件化和工程化的人、能兜住性能与兼容的人。
要求：不要写“我看了 JD / 这个岗位”，不要写得像结论报告。

第 2 段只写：我为什么适合这类场景。
要求：只拿 1 个最像 JD 场景的真实经历来写，不要并排堆多个案例。
要求：顺序就是“当时遇到什么问题，我怎么处理，最后把什么事情做顺了”。
要求：不要讲职责概述，要讲具体问题；也不要讲“匹配、对齐、贴合”，而是让人读完自然感觉到“这种页面交付 / 联调 / 多端协作的活你做过”。
要求：写完场景后，要顺手点一下放到这个岗位里会怎么用上，例如页面交付、组件化开发、联调推进、性能治理、设备交互、多端协作。

第 3 段只写：我为什么愿意继续深入这个方向。
要求：写我对这种前端交付方式、工程模式或协作方式的认可，不要重复第 2 段证据。
要求：这一段控制得短一些，讲清“为什么认可”即可，不要展开成大段方法论。

第 4 段只写：补充亮点或快速补齐能力。
要求：只补 1 个辅助点，收尾自然。
要求：补充点优先选可迁移到这个岗位的能力，例如 Vue/TypeScript 联调、工程规范、可视化、设备对接、AI 工具使用习惯，而不是再讲一遍主轴。

额外要求：
- 只输出最终文案，不要解释。
- 总长度尽量在 300 到 400 字之间。
- 不要写“您好/你好/非常感兴趣/希望有机会/期待沟通”这类求职话术。
- 不要出现项目名、公司名、平台名，不要编造经历或结果。
- 技术术语要克制，重点写“判断”和“证据”，不要写成技能清单。
- 如果 JD 重点在 Vue / TypeScript / 工程化，就围绕组件化、联调、性能、规范来写；如果重点在多端 / 小程序 / 设备配合，就围绕多端交付、适配、协同来写。
- 更像真实沟通，不要像在逐条响应 JD。

输出前自检：
1. 是否严格 4 段。
2. 第 2 段是否有具体问题证据，而不是职责概述。
3. 第 2 段是否回到了 JD 里的前端场景，而不是抽象谈匹配。
4. 第 1 段是否足够具体，第 3 段是否足够克制，第 4 段是否只是补充而不是重复主轴。
5. 是否像真人消息，而不是简历摘要。

请直接返回最终文案。"""

    def _build_jd_text(self, jd: JobDescription) -> str:
        parts = [
            jd.job_requirements or "",
            jd.job_description or "",
            ", ".join(jd.tags or []),
        ]
        return "\n".join(part for part in parts if part).strip()

    def _build_resume_text(self, resume: ResumeProfile) -> str:
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

    def _count_visible_chars(self, text: str) -> int:
        return len(re.sub(r"\s+", "", text or ""))

    def _split_paragraphs(self, text: str) -> list[str]:
        return [part.strip() for part in re.split(r"\n\s*\n|\n", text or "") if part.strip()]

    def _validate_output(self, text: str) -> tuple[bool, list[str]]:
        issues: list[str] = []
        paragraphs = self._split_paragraphs(text)
        char_count = self._count_visible_chars(text)
        if len(paragraphs) != 4:
            issues.append(f"当前只有 {len(paragraphs)} 段，必须严格为 4 段。")
        if char_count < 300:
            issues.append(f"当前字数为 {char_count}，低于 300。")
        if char_count > 420:
            issues.append(f"当前字数为 {char_count}，超过 420。")
        return not issues, issues

    def _rewrite_with_feedback(
        self,
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
            "5. 保留原本的前端场景判断和经历主轴，但把结构改对。\n"
            f"原输出：\n{draft.strip()}"
        )
        retry_messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": feedback},
        ]
        return self.client.chat(retry_messages, temperature=0.6, max_tokens=800)

    def _append_postscript(self, text: str) -> str:
        cleaned = (text or "").strip()
        postscript = self.GREETING_POSTSCRIPT.strip()
        if not postscript:
            return cleaned
        return f"{cleaned}\n({postscript})" if cleaned else f"({postscript})"


__all__ = ["FrontendGreetingModel"]
