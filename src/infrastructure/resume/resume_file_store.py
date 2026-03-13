"""简历管理模块"""
import json
from pathlib import Path
from typing import Optional

from src.models.resume_profile import ResumeProfile
from src.config.settings import Config


class ResumeFileStore:
    """简历管理器"""

    def __init__(self):
        """初始化简历管理器"""
        Config.ensure_dirs()
        self.resume_file = Config.RESUME_FILE
        self._resume: Optional[ResumeProfile] = None

    def load_resume(self) -> Optional[ResumeProfile]:
        """
        从文件加载简历

        Returns:
            Resume对象
        """
        if not self.resume_file.exists():
            return None

        try:
            with open(self.resume_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._resume = ResumeProfile(**data)
                return self._resume
        except Exception as e:
            print(f"加载简历失败: {e}")
            return None

    def save_resume(self, resume: ResumeProfile) -> bool:
        """
        保存简历到文件

        Args:
            resume: Resume对象

        Returns:
            是否保存成功
        """
        try:
            with open(self.resume_file, 'w', encoding='utf-8') as f:
                json.dump(resume.model_dump(), f, ensure_ascii=False, indent=2)
            self._resume = resume
            return True
        except Exception as e:
            print(f"保存简历失败: {e}")
            return False

    def get_resume_text(self, resume: Optional[ResumeProfile] = None) -> str:
        """
        将简历转换为文本格式，用于LLM分析

        Args:
            resume: Resume对象，如果不传则使用已加载的简历

        Returns:
            简历文本
        """
        resume = resume or self._resume
        if not resume:
            return ""

        lines = [
            f"姓名: {resume.name}",
            f"手机: {resume.phone}",
            f"邮箱: {resume.email}",
            f"目标职位: {resume.target_position}",
            f"期望薪资: {resume.target_salary}",
            f"期望地点: {resume.target_location}",
            f"工作年限: {resume.years_of_experience}",
            "",
            "技能:",
            ", ".join(resume.skills),
            "",
            "个人优势:",
        ]

        for advantage in resume.advantages:
            lines.append(f"- {advantage}")

        if resume.self_introduction:
            lines.extend(["", "自我介绍:", resume.self_introduction])

        if resume.education:
            lines.extend(["", "教育经历:"])
            for edu in resume.education:
                lines.append(f"- {edu.school} | {edu.major} | {edu.degree} | {edu.graduation_date}")

        if resume.work_experience:
            lines.extend(["", "工作经历:"])
            for work in resume.work_experience:
                end_date = work.end_date or "至今"
                lines.append(f"- {work.company} | {work.position} | {work.start_date} - {end_date}")
                lines.append(f"  {work.description}")

        if resume.project_experience:
            lines.extend(["", "项目经历:"])
            for proj in resume.project_experience:
                lines.append(f"- {proj.name} | {proj.role}")
                lines.append(f"  技术栈: {', '.join(proj.technologies)}")
                lines.append(f"  {proj.description}")

        return "\n".join(lines)

    def create_sample_resume(self) -> ResumeProfile:
        """创建示例简历（供测试使用）"""
        return ResumeProfile(
            name="张三",
            phone="13800138000",
            email="zhangsan@example.com",
            target_position="Python开发工程师",
            target_salary="20K-30K",
            target_location="北京",
            years_of_experience="5年",
            skills=[
                "Python", "Django", "Flask", "FastAPI",
                "MySQL", "PostgreSQL", "Redis", "MongoDB",
                "Docker", "Kubernetes", "Nginx",
                "Git", "CI/CD", "AWS", "Linux"
            ],
            advantages=[
                "5年Python后端开发经验",
                "2年团队管理经验",
                "有高并发系统设计经验",
                "参与过日活百万级用户项目",
                "开源项目贡献者"
            ],
            self_introduction="我是一名热爱技术的Python开发者，有5年后端开发经验，擅长构建高可用、高性能的系统架构。",
        )
