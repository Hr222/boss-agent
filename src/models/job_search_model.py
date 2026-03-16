"""抓取模型：负责岗位搜索与落库流程编排。"""

from dataclasses import dataclass

from src.infrastructure.browser.boss_search_client import (
    BossSearchClient,
    BossSearchOptions,
    SearchCollectionSummary,
)
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
    """协调 Boss 搜索抓取与岗位落库。

    这里是“搜索用例层”：负责把搜索参数组装给浏览器抓取客户端，并把结果对象返回给上层。
    真正的页面滚动、卡片读取、续抓游标等细节都收敛在 browser client。
    """

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

    async def search_jobs(self, request: JobSearchRequest) -> SearchCollectionSummary:
        """执行抓取流程，并返回基础统计。"""
        self.use_repository(JobRepository(request.db_path))
        # request 是控制层输入模型，options 是浏览器层选项模型；
        # 两者分开可以避免页面能力直接渗透到控制层。
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


__all__ = ["JobSearchModel", "JobSearchRequest", "SearchCollectionSummary"]
