"""闭环求职 Agent：串联抓取、匹配、入队与投递。"""

from dataclasses import dataclass
from pathlib import Path

from src.config.settings import Config
from src.infrastructure.browser.boss_search_client import BossSearchClient, BossSearchOptions
from src.models.resume_store import ResumeStore
from src.models.boss_apply_browser import BossApplyBrowserModel, BossApplyOptions
from src.models.job_repository import JobRepository
from src.models.job_screening_model import JobScreeningModel


@dataclass(frozen=True)
class JobAgentFlowRequest:
    """一键求职 Agent 的运行参数。"""

    db_path: str = "data/boss_jobs.sqlite3"
    keyword: str = ""
    city: str = ""
    city_code: str = ""
    target_apply_count: int = 15
    min_match_batch_size: int = 5
    strategy_id: str = "backend_ai"
    screening_threshold: float = 75
    greetings_dir: str = "data/greetings"
    require_login: bool = True
    debug: bool = False


class JobAgentFlowModel:
    """负责执行抓取 -> 匹配 -> 入队 -> 投递的闭环流程。"""

    def __init__(
        self,
        repository: JobRepository | None = None,
        search_client: BossSearchClient | None = None,
        screening_model: JobScreeningModel | None = None,
        apply_browser_model: BossApplyBrowserModel | None = None,
    ) -> None:
        self.repository = repository or JobRepository()
        self.search_client = search_client or BossSearchClient()
        self.screening_model = screening_model or JobScreeningModel()
        self.apply_browser_model = apply_browser_model or BossApplyBrowserModel()
        self.resume_store = ResumeStore()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前使用的岗位仓储。"""
        self.repository = repository
        self.screening_model.use_repository(repository)

    async def run(self, request: JobAgentFlowRequest) -> dict:
        """运行闭环 Agent，直到实际发送数量达到目标值。"""
        repository = JobRepository(request.db_path)
        self.use_repository(repository)
        self.screening_model.use_strategy(request.strategy_id)
        Config.resolve_project_path(request.greetings_dir).mkdir(parents=True, exist_ok=True)

        browser = await self.apply_browser_model._start_browser()
        session_seen_urls: set[str] = set()
        total_sent_count = 0
        total_already_contacted_count = 0

        excluded_company_names = self._load_excluded_company_names()
        # 搜索客户端内部仍需要一个 limit 字段，但闭环 Agent 不再对用户暴露该参数。
        # 这里用目标投递数作为初始搜索基数，后续每轮再按剩余待完成数量动态递减。
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
            search_tab = await self.search_client.prepare_search_tab(browser, search_options)

            while total_sent_count < request.target_apply_count:
                remaining_apply_count = request.target_apply_count - total_sent_count
                ready_count = repository.count_ready_to_apply_jobs()

                # 当前没有可投递岗位时，先抓取并匹配一轮。
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
                        f"[agent] 抓取完成：新链接 {collect_stats['new_links_found']}，"
                        f"新岗位 {collect_stats['new_jobs_written']}。"
                    )

                    # “写库成功”不代表“待匹配成功”。
                    # 如果这些岗位只是历史岗位被更新了一遍，它们可能已存在 suitability 结果，
                    # 此时 get_pending_jobs 会返回 0。闭环主流程应以真实待匹配数量为准。
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
                    screening_results = (
                        self.screening_model.analyze_pending_jobs(
                            limit=screening_limit,
                            threshold=request.screening_threshold,
                            out_dir=request.greetings_dir,
                        )
                        if screening_limit > 0
                        else []
                    )
                    suitable_count = sum(int(item.get("is_suitable", 0)) for item in screening_results if item.get("status") == "ok")
                    print(
                        f"[agent] 匹配完成：分析 {len(screening_results)} 个岗位，"
                        f"新增入队 {suitable_count} 个。"
                    )

                    ready_count = repository.count_ready_to_apply_jobs()
                    print(f"[agent] 当前待投递队列：{ready_count} 个。")
                    if ready_count <= 0:
                        # 这一轮没有匹配出可投递岗位，就继续下一轮抓取。
                        continue

                # 这一轮只要队列里已有岗位，就把当前已入队岗位全部发完。
                # 这样即使在本轮发送过程中已经达到用户目标，也不会把同轮已匹配成功的岗位截断留到下次。
                queue = repository.get_ready_to_apply_jobs(limit=ready_count)
                apply_options = BossApplyOptions(
                    require_login=False,
                    dry_run=False,
                    fill_only=False,
                    no_close_tab=False,
                    greetings_dir=request.greetings_dir,
                    debug=request.debug,
                    target_apply_count=None,
                )
                apply_results = await self.apply_browser_model.apply_jobs(
                    queue,
                    mark_applied=repository.mark_applied,
                    options=apply_options,
                    browser=browser,
                )
                sent_this_round = sum(1 for item in apply_results if item.get("status") == "ok")
                already_contacted_this_round = sum(1 for item in apply_results if item.get("reason") == "already_contacted")
                total_sent_count += sent_this_round
                total_already_contacted_count += already_contacted_this_round
                print(
                    f"[agent] 投递完成：本轮实际发送 {sent_this_round} 个，"
                    f"继续沟通/已沟通 {already_contacted_this_round} 个，"
                    f"累计实际发送 {total_sent_count}/{request.target_apply_count}。"
                )

            return {
                "status": "completed",
                "target_apply_count": request.target_apply_count,
                "sent_count": total_sent_count,
                "already_contacted_count": total_already_contacted_count,
                "ready_count": repository.count_ready_to_apply_jobs(),
            }
        finally:
            await self.apply_browser_model._safe_close_browser(browser, debug=request.debug)

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


__all__ = ["JobAgentFlowModel", "JobAgentFlowRequest"]
