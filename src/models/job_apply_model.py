"""投递模型：负责驱动已入队岗位的浏览器投递流程。"""

from dataclasses import dataclass
import os

from src.infrastructure.browser.boss_apply import ApplyJobResult
from src.models.boss_apply_facade import BossApplyFacade, BossApplyOptions
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


@dataclass(frozen=True)
class JobApplySummary:
    """批量投递结果汇总。"""

    results: list[ApplyJobResult]

    @property
    def processed_count(self) -> int:
        """本轮已处理岗位总数。"""
        return len(self.results)

    @property
    def sent_count(self) -> int:
        """本轮实际发送成功的岗位数。"""
        return sum(1 for item in self.results if item.status == "ok")

    @property
    def already_contacted_count(self) -> int:
        """本轮因已沟通而跳过的岗位数。"""
        return sum(1 for item in self.results if item.reason == "already_contacted")

    @property
    def skipped_count(self) -> int:
        """本轮普通跳过的岗位数。"""
        return sum(
            1 for item in self.results if item.status == "skipped" and item.reason != "already_contacted"
        )

    @property
    def failed_count(self) -> int:
        """本轮发送失败的岗位数。"""
        return sum(1 for item in self.results if item.status == "failed")


class JobApplyModel:
    """读取待投递岗位，并驱动浏览器自动化投递。

    这里属于“投递用例层”：负责决定从仓储取哪些岗位、以什么投递参数调用浏览器门面。
    页面模板识别、输入框处理、发送校验等细节都不放在这里。
    """

    def __init__(
        self,
        repository: JobRepository | None = None,
        apply_facade: BossApplyFacade | None = None,
    ) -> None:
        """初始化岗位仓储与投递门面。"""
        self.repository = repository or JobRepository()
        self.apply_facade = apply_facade or BossApplyFacade()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前使用的岗位仓储。"""
        self.repository = repository

    async def apply_ready_jobs(self, request: JobApplyRequest) -> JobApplySummary:
        """根据请求执行批量投递，或处理单岗位预览。"""
        self.use_repository(JobRepository(request.db_path))
        if request.job_url:
            queue = [{"job_url": request.job_url, "raw_json": None}]
        else:
            # 批量模式下按“成功数”收口，因此这里先多取一批未投递岗位，
            # 让失败项不会直接吃掉本轮 15 次额度。
            queue_limit = max(request.limit * 5, 50)
            queue = self.repository.get_ready_to_apply_jobs(limit=queue_limit)

        # 这里统一把 CLI/Agent 的参数折叠成浏览器层可消费的选项对象，
        # 避免上层直接感知 nodriver 细节。
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
            apply_retries=max(int(os.getenv("BOSS_APPLY_RETRIES", "2")), 0),
            max_apply_failures=max(int(os.getenv("BOSS_APPLY_MAX_FAILURES", "3")), 1),
        )
        results = await self.apply_facade.apply_jobs(
            queue,
            mark_applied=self.repository.mark_applied,
            mark_apply_failed=self.repository.mark_apply_failed,
            options=options,
        )
        return JobApplySummary(results=results)

__all__ = ["JobApplyModel", "JobApplyRequest", "JobApplySummary"]
