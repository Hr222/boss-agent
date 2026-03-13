"""投递模型：负责驱动已入队岗位的浏览器投递流程。"""

from dataclasses import dataclass

from src.models.boss_apply_browser import BossApplyBrowserModel, BossApplyOptions
from src.models.job_repository import JobRepository


@dataclass(frozen=True)
class JobApplyRequest:
    """自动投递请求参数。"""

    db_path: str = "data/boss_jobs.sqlite3"
    # 这里的 limit 表示“成功处理”的目标数量，而不是只取多少条记录。
    limit: int = 15
    require_login: bool = False
    dry_run: bool = False
    fill_only: bool = False
    no_close_tab: bool = False
    greetings_dir: str = "data/greetings"
    job_url: str | None = None
    greeting_file: str | None = None
    greeting_text: str | None = None
    debug: bool = False


class JobApplyModel:
    """读取待投递岗位，并驱动浏览器自动化投递。"""

    def __init__(
        self,
        repository: JobRepository | None = None,
        browser_model: BossApplyBrowserModel | None = None,
    ) -> None:
        """初始化岗位仓储与浏览器模型。"""
        self.repository = repository or JobRepository()
        self.browser_model = browser_model or BossApplyBrowserModel()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前使用的岗位仓储。"""
        self.repository = repository

    async def apply_ready_jobs(self, request: JobApplyRequest) -> list[dict]:
        """根据请求执行批量投递，或处理单岗位预览。"""
        self.use_repository(JobRepository(request.db_path))
        if request.job_url:
            queue = [{"job_url": request.job_url, "raw_json": None}]
        else:
            # 批量模式下按“成功数”收口，因此这里先多取一批未投递岗位，
            # 让失败项不会直接吃掉本轮 15 次额度。
            queue_limit = max(request.limit * 5, 50)
            queue = self.repository.get_ready_to_apply_jobs(limit=queue_limit)

        options = BossApplyOptions(
            require_login=request.require_login,
            dry_run=request.dry_run,
            fill_only=request.fill_only,
            no_close_tab=request.no_close_tab,
            greetings_dir=request.greetings_dir,
            job_url=request.job_url,
            greeting_file=request.greeting_file,
            greeting_text=request.greeting_text,
            debug=request.debug,
            target_apply_count=None if request.job_url else request.limit,
        )
        return await self.browser_model.apply_jobs(
            queue,
            mark_applied=self.repository.mark_applied,
            options=options,
        )


__all__ = ["JobApplyModel", "JobApplyRequest"]
