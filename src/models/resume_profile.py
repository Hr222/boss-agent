"""Resume data models for MVC architecture."""

from typing import List, Optional

from pydantic import BaseModel, Field


class WorkExperience(BaseModel):
    """Work experience."""

    company: str = Field(description="公司名称")
    position: str = Field(description="职位")
    start_date: str = Field(description="开始时间")
    end_date: Optional[str] = Field(None, description="结束时间，在职则为空")
    description: str = Field(description="工作描述")


class ProjectExperience(BaseModel):
    """Project experience."""

    name: str = Field(description="项目名称")
    role: str = Field(description="担任角色")
    description: str = Field(description="项目描述")
    technologies: List[str] = Field(default_factory=list, description="使用技术")


class Education(BaseModel):
    """Education."""

    school: str = Field(description="学校名称")
    major: str = Field(description="专业")
    degree: str = Field(description="学历")
    graduation_date: str = Field(description="毕业时间")


class ResumeProfile(BaseModel):
    """Resume profile model."""

    name: str = Field(description="姓名")
    phone: str = Field(description="手机号")
    email: str = Field(description="邮箱")
    target_position: str = Field(description="目标职位")
    target_salary: str = Field(description="期望薪资")
    target_location: str = Field(description="期望工作地点")
    years_of_experience: str = Field(description="工作年限")
    education: List[Education] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    project_experience: List[ProjectExperience] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list, description="技能标签")
    advantages: List[str] = Field(default_factory=list, description="个人优势")
    self_introduction: Optional[str] = Field(None, description="自我介绍")
    excluded_company_names: List[str] = Field(default_factory=list, description="抓取阶段需要过滤的公司名单")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "张三",
                "phone": "13800138000",
                "email": "zhangsan@example.com",
                "target_position": "Python开发工程师",
                "target_salary": "20K-30K",
                "target_location": "北京",
                "years_of_experience": "5年",
                "skills": ["Python", "Django", "MySQL", "Redis"],
                "advantages": ["3年大厂经验", "全栈开发能力", "团队管理经验"],
            }
        }


__all__ = ["Education", "ProjectExperience", "ResumeProfile", "WorkExperience"]
