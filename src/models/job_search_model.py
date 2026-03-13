"""抓取模型：负责岗位搜索与落库流程编排。"""

from dataclasses import dataclass

from src.infrastructure.browser.boss_search_client import BossSearchClient, BossSearchOptions
from src.models.job_repository import JobRepository


@dataclass(frozen=True)
class JobSearchRequest:
    """岗位抓取请求参数。"""

    db_path: str = "data/boss_jobs.sqlite3"
    keyword: str = "Python开发"
    city: str = "深圳"
    city_code: str = ""
    limit: int = 20
    require_login: bool = False
    no_collect: bool = False
    debug: bool = False
    exclude_company_names: tuple[str, ...] = ()


class JobSearchModel:
    """协调 Boss 搜索抓取与岗位落库。"""

    def __init__(
        self,
        repository: JobRepository | None = None,
        browser_client: BossSearchClient | None = None,
    ) -> None:
        """初始化仓储与浏览器抓取客户端。"""
        self.repository = repository or JobRepository()
        self.browser_client = browser_client or BossSearchClient()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前使用的岗位仓储。"""
        self.repository = repository

    async def search_jobs(self, request: JobSearchRequest) -> dict:
        """执行抓取流程，并返回基础统计。"""
        self.use_repository(JobRepository(request.db_path))
        options = BossSearchOptions(
            keyword=request.keyword,
            city=request.city,
            city_code=request.city_code,
            limit=request.limit,
            require_login=request.require_login,
            no_collect=request.no_collect,
            debug=request.debug,
            exclude_company_names=request.exclude_company_names,
        )
        return await self.browser_client.collect_jobs(repository=self.repository, options=options)


__all__ = ["JobSearchModel", "JobSearchRequest"]
