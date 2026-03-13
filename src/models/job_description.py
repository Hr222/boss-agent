"""JD data model for MVC architecture."""

from typing import List, Optional

from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    """Job description model."""

    job_id: str = Field(description="职位ID")
    job_title: str = Field(description="职位名称")
    company_name: str = Field(description="公司名称")
    salary_range: str = Field(description="薪资范围")
    location: str = Field(description="工作地点")
    job_requirements: str = Field(description="职位要求")
    job_description: str = Field(description="职位描述")
    tags: List[str] = Field(default_factory=list, description="职位标签")
    hr_name: Optional[str] = Field(None, description="HR姓名")
    hr_title: Optional[str] = Field(None, description="HR职位")
    hr_active_time: Optional[str] = Field(None, description="HR活跃时间")
    job_url: str = Field(description="职位链接")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "123456",
                "job_title": "Python开发工程师",
                "company_name": "某某科技公司",
                "salary_range": "15K-25K",
                "location": "北京·朝阳区",
                "job_requirements": "1. 3年以上Python开发经验...",
                "job_description": "负责后端系统开发...",
                "tags": ["Python", "Django", "MySQL"],
                "hr_name": "王女士",
                "hr_title": "招聘专员",
                "job_url": "https://www.zhipin.com/job_detail/123456",
            }
        }


__all__ = ["JobDescription"]
