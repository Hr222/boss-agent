"""Match result model for MVC architecture."""

from typing import List

from pydantic import BaseModel, Field


class JobMatchResult(BaseModel):
    """JD and resume match result."""

    job_id: str = Field(description="职位ID")
    job_title: str = Field(description="职位名称")
    company_name: str = Field(description="公司名称")
    match_score: float = Field(description="匹配度分数 (0-100)")
    match_level: str = Field(description="匹配等级: 高/中/低")
    matched_skills: List[str] = Field(default_factory=list, description="匹配的技能")
    missing_skills: List[str] = Field(default_factory=list, description="缺失的技能")
    matched_experience: List[str] = Field(default_factory=list, description="匹配的经验")
    advantages: List[str] = Field(default_factory=list, description="个人优势匹配点")
    analysis: str = Field(description="详细匹配分析")
    suggestions: List[str] = Field(default_factory=list, description="求职建议")
    greeting_message: str = Field(description="生成的打招呼语")
    is_recommended: bool = Field(description="是否推荐投递")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "123456",
                "job_title": "Python开发工程师",
                "company_name": "某某科技公司",
                "match_score": 85.5,
                "match_level": "高",
                "matched_skills": ["Python", "Django", "MySQL"],
                "missing_skills": ["Kubernetes"],
                "matched_experience": ["3年Web开发经验", "高并发项目经验"],
                "advantages": ["全栈开发能力", "大厂背景"],
                "analysis": "您的技能与JD高度匹配...",
                "suggestions": ["可以重点强调高并发经验"],
                "greeting_message": "您好，我对贵司的Python开发岗位很感兴趣...",
                "is_recommended": True,
            }
        }


__all__ = ["JobMatchResult"]
