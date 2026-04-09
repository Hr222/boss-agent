"""求职 Agent：负责执行搜索、筛选、入队与投递的闭环流程。"""

from dataclasses import asdict, dataclass
import os

from src.config.settings import Config
from src.infrastructure.browser.boss_search_client import BossSearchClient, BossSearchOptions
from src.models.boss_apply_facade import BossApplyFacade, BossApplyOptions
from src.models.job_apply_model import JobApplySummary
from src.models.job_repository import JobRepository
from src.models.job_screening_model import JobScreeningModel, ScreeningJobResult
from src.models.resume_store import ResumeStore


@dataclass(frozen=True)
class JobApplicationAgentRequest:
    """求职 Agent 运行参数。"""

    db_path: str = "data/boss_jobs.sqlite3"
    keyword: str = ""
    city: str = ""
    city_code: str = ""
    target_apply_count: int = 15
    min_match_batch_size: int = 5
    strategy_id: str = "backend_ai"
    llm_provider: str = "zhipu"
    screening_threshold: float = 75
    greetings_dir: str = "data/greetings"
    require_login: bool = True
    debug: bool = False


@dataclass(frozen=True)
class AgentRunSummary:
    """求职 Agent 单次运行汇总。"""

    status: str
    target_apply_count: int
    sent_count: int
    already_contacted_count: int
    ready_count: int

    def to_dict(self) -> dict:
        """兼容现有控制台与命令行展示。"""
        return asdict(self)


class JobApplicationAgent:
    """执行搜索、筛选、投递闭环的核心 Agent。

    这里是“流程编排层”，负责决定每一轮先抓多少、筛多少、投多少。
    它不直接处理页面细节，也不直接实现匹配规则；这些能力分别下沉到
    search client、screening model 和 apply facade。
    """

    def __init__(
        self,
        repository: JobRepository | None = None,
        search_client: BossSearchClient | None = None,
        screening_service: JobScreeningModel | None = None,
        apply_facade: BossApplyFacade | None = None,
    ) -> None:
        self.repository = repository or JobRepository()
        self.search_client = search_client or BossSearchClient()
        self.screening_service = screening_service or JobScreeningModel()
        self.apply_facade = apply_facade or BossApplyFacade()
        self.resume_store = ResumeStore()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前 Agent 使用的岗位仓储。"""
        self.repository = repository
        self.screening_service.use_repository(repository)

    async def run(self, request: JobApplicationAgentRequest) -> AgentRunSummary:
        """运行闭环 Agent，直到实际发送数量达到目标值。"""
        repository = JobRepository(request.db_path)
        self.use_repository(repository)
        self.screening_service.use_strategy(request.strategy_id)
        self.screening_service.use_llm_provider(request.llm_provider)
        Config.resolve_project_path(request.greetings_dir).mkdir(parents=True, exist_ok=True)

        browser = await self.apply_facade._start_browser()
        session_seen_urls: set[str] = set()
        total_sent_count = 0
        total_already_contacted_count = 0

        excluded_company_names = self._load_excluded_company_names()
        search_options = BossSearchOptions(
            keyword=request.keyword,
            city=request.city,
            city_code=request.city_code,
            limit=max(1, int(request.target_apply_count)),
            require_login=request.require_login,
            no_collect=False,
            debug=request.debug,
            exclude_company_names=excluded_company_names,
        )

        try:
            if excluded_company_names:
                print(f"[agent] 已启用历史公司过滤：{', '.join(excluded_company_names)}")
            print(f"[agent] 当前匹配策略：{request.strategy_id}")
            print(f"[agent] 当前 LLM 提供方：{request.llm_provider}")
            search_tab = await self.search_client.prepare_search_tab(browser, search_options)

            while total_sent_count < request.target_apply_count:
                # 闭环收口标准是“实际发送成功数”，不是“进入队列数”或“已沟通数”。
                remaining_apply_count = request.target_apply_count - total_sent_count
                ready_count = repository.count_ready_to_apply_jobs()

                if ready_count <= 0:
                    print(
                        f"\n[agent] 开始补充投递队列："
                        f"当前待发送 {remaining_apply_count} 个，待投递队列 {ready_count} 个。"
                    )
                    collect_stats = await self.search_client.collect_jobs_from_tab(
                        search_tab,
                        repository=repository,
                        options=search_options,
                        session_seen_urls=session_seen_urls,
                        target_new_jobs=self._get_round_batch_size(
                            remaining_apply_count,
                            request.min_match_batch_size,
                        ),
                    )
                    print(
                        f"[agent] 抓取完成：新链接 {collect_stats.new_links_found}，"
                        f"新岗位 {collect_stats.new_jobs_written}。"
                    )

                    # 只消化本轮新增待分析岗位，避免一次性把历史积压全部吞掉。
                    pending_count = repository.count_pending_jobs()
                    screening_limit = min(
                        max(0, pending_count),
                        self._get_round_batch_size(remaining_apply_count, request.min_match_batch_size),
                    )
                    if screening_limit <= 0:
                        print(
                            "[agent] 本轮抓取后没有新增待匹配岗位："
                            "本轮抓到的岗位可能是历史已分析记录，或当前页面未加载出新的未分析岗位。"
                        )
                    screening_results: list[ScreeningJobResult] = (
                        self.screening_service.analyze_pending_jobs(
                            limit=screening_limit,
                            threshold=request.screening_threshold,
                        )
                        if screening_limit > 0
                        else []
                    )
                    suitable_count = sum(
                        int(item.is_suitable)
                        for item in screening_results
                        if item.status == "ok"
                    )
                    print(
                        f"[agent] 匹配完成：分析 {len(screening_results)} 个岗位，"
                        f"新增入队 {suitable_count} 个。"
                    )

                    ready_count = repository.count_ready_to_apply_jobs()
                    print(f"[agent] 当前待投递队列：{ready_count} 个。")
                    if ready_count <= 0:
                        continue

                # 进入投递阶段后，优先清空当前待投递队列，保证队列状态单调收敛。
                queue = repository.get_ready_to_apply_jobs(limit=ready_count)
                apply_options = BossApplyOptions(
                    require_login=False,
                    dry_run=False,
                    fill_only=False,
                    no_close_tab=False,
                    greetings_dir=request.greetings_dir,
                    debug=request.debug,
                    target_apply_count=None,
                    apply_retries=max(int(os.getenv("BOSS_APPLY_RETRIES", "2")), 0),
                    max_apply_failures=max(int(os.getenv("BOSS_APPLY_MAX_FAILURES", "3")), 1),
                )
                apply_results = JobApplySummary(
                    results=await self.apply_facade.apply_jobs(
                    queue,
                    mark_applied=repository.mark_applied,
                    mark_apply_skipped=repository.mark_apply_skipped,
                    mark_apply_failed=repository.mark_apply_failed,
                    options=apply_options,
                    browser=browser,
                    )
                )
                sent_this_round = apply_results.sent_count
                already_contacted_this_round = apply_results.already_contacted_count
                total_sent_count += sent_this_round
                total_already_contacted_count += already_contacted_this_round
                print(
                    f"[agent] 投递完成：本轮实际发送 {sent_this_round} 个，"
                    f"继续沟通/已沟通 {already_contacted_this_round} 个，"
                    f"累计实际发送 {total_sent_count}/{request.target_apply_count}。"
                )

            return AgentRunSummary(
                status="completed",
                target_apply_count=request.target_apply_count,
                sent_count=total_sent_count,
                already_contacted_count=total_already_contacted_count,
                ready_count=repository.count_ready_to_apply_jobs(),
            )
        finally:
            await self.apply_facade._safe_close_browser(browser, debug=request.debug)

    def _load_excluded_company_names(self) -> tuple[str, ...]:
        """优先读取简历显式配置的过滤公司名单，未配置时回退到历史任职公司。"""
        resume = self.resume_store.load_resume()
        if not resume:
            return ()
        names: list[str] = []
        explicit_names = [item.strip() for item in getattr(resume, "excluded_company_names", []) if (item or "").strip()]
        if explicit_names:
            names.extend(explicit_names)
        else:
            names.extend(
                work.company.strip()
                for work in resume.work_experience
                if (work.company or "").strip()
            )

        unique_names: list[str] = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)
        return tuple(unique_names)

    def _get_round_batch_size(self, remaining_apply_count: int, min_match_batch_size: int) -> int:
        """按剩余待完成投递数决定本轮抓取基数，并对最小批次做 5-10 钳制。"""
        clamped_batch_size = min(max(int(min_match_batch_size), 5), 10)
        return max(clamped_batch_size, int(remaining_apply_count))


__all__ = ["AgentRunSummary", "JobApplicationAgent", "JobApplicationAgentRequest"]
