"""控制台控制器：负责把用户输入路由到对应模型。"""

import asyncio
import os
from pathlib import Path

from src.config.settings import Config
from src.infrastructure.browser.nodriver_runtime import _env_bool
from src.models.job_apply_model import JobApplyModel, JobApplyRequest
from src.models.job_application_agent import JobApplicationAgent, JobApplicationAgentRequest
from src.models.job_repository import JobRepository
from src.models.job_screening_model import JobScreeningModel
from src.models.manual_job_model import ManualJobModel
from src.models.resume_profile import ResumeProfile
from src.models.resume_store import ResumeStore
from src.views.console_view import ConsoleView

_BOSS_ORIGIN = "https://www.zhipin.com"


class ConsoleController:
    """协调 View 与 Model 的主控制器。"""

    def __init__(
        self,
        view: ConsoleView | None = None,
        resume_store: ResumeStore | None = None,
        manual_job_model: ManualJobModel | None = None,
        job_screening_model: JobScreeningModel | None = None,
        job_apply_model: JobApplyModel | None = None,
        job_application_agent: JobApplicationAgent | None = None,
    ) -> None:
        self.view = view or ConsoleView()
        self.resume_store = resume_store or ResumeStore()
        self.manual_job_model = manual_job_model or ManualJobModel()
        self.job_screening_model = job_screening_model or JobScreeningModel()
        self.job_apply_model = job_apply_model or JobApplyModel()
        self.job_application_agent = job_application_agent or JobApplicationAgent()

    def run(self) -> None:
        """运行主菜单循环。"""
        self.view.show_banner()
        self._ensure_api_key()
        resume = self._ensure_resume()
        self.view.show_current_resume(resume)

        while True:
            choice = self.view.get_main_menu_choice()
            if choice == "0":
                self.view.show_goodbye()
                break
            if choice == "1":
                self._handle_manual_job(resume)
                continue
            if choice == "2":
                resume = self._handle_resume_menu()
                continue
            if choice == "3":
                self._show_history()
                continue
            if choice == "4":
                self._handle_batch_screening()
                continue
            if choice == "5":
                self._handle_job_apply()
                continue
            if choice == "6":
                self._handle_agent_flow()
                continue
            if choice == "7":
                self._handle_rescore_queue()
                continue
            self.view.show_invalid_choice()

    def _ensure_api_key(self) -> None:
        """在进入主流程前统一校验 LLM Key。"""
        api_key = Config.get_llm_api_key()
        if not api_key or api_key == "your_api_key_here":
            print("\n⚠️  请先配置 Z.ai / 智谱 API Key！")
            print("\n获取方式: https://open.bigmodel.cn/ 或 https://docs.z.ai/")
            print("配置方法: 编辑 .env 文件，优先设置 ZAI_API_KEY（兼容旧的 ZHIPUAI_API_KEY）")
            raise SystemExit(1)

    def _ensure_resume(self) -> ResumeProfile:
        """保证当前系统内有一份可用简历。"""
        resume = self.resume_store.load_resume()
        if resume:
            return resume
        print("\n未找到简历，请先创建简历")
        self._create_resume()
        resume = self.resume_store.load_resume()
        if not resume:
            raise RuntimeError("简历创建后仍未能成功加载。")
        return resume

    def _handle_manual_job(self, resume: ResumeProfile) -> None:
        """处理手动粘贴 JD 的单岗位分析流程。"""
        jd_info = self.view.collect_manual_job()
        if not jd_info["job_requirements"]:
            self.view.show_empty_job_description()
            return
        strategy_id = self.view.prompt_strategy_selection()
        self.manual_job_model.use_strategy(strategy_id, resume)
        self.view.show_manual_job_start(jd_info)
        result = self.manual_job_model.analyze_manual_job(jd_info, resume)
        if result is None:
            self.view.show_manual_job_failed()
            return
        self.view.show_manual_match_result(result)
        if self.view.confirm_save_result():
            filepath = self._save_result(
                jd_info=jd_info,
                match_result={
                    "match_score": result.match_score,
                    "match_level": result.match_level,
                    "matched_skills": result.matched_skills,
                    "missing_skills": result.missing_skills,
                    "matched_experience": result.matched_experience,
                    "advantages": result.advantages,
                    "analysis": result.analysis,
                    "suggestions": result.suggestions,
                    "is_recommended": result.is_recommended,
                },
                greeting=result.greeting_message,
            )
            self.view.show_saved_result(filepath)

    def _handle_resume_menu(self) -> ResumeProfile:
        """处理简历查看和更新入口。"""
        if self.view.prompt_resume_action() == "u":
            self._create_resume()
        resume = self.resume_store.load_resume()
        if resume:
            self.view.show_resume_summary(resume)
            return resume
        raise RuntimeError("简历加载失败。")

    def _create_resume(self) -> None:
        """采集简历字段并落盘。"""
        data = self.view.collect_resume_fields()
        resume = ResumeProfile(**data)
        if self.resume_store.save_resume(resume):
            self.view.show_resume_saved()

    def _show_history(self) -> None:
        """展示历史生成的招呼语文件。"""
        Config.ensure_dirs()
        files = list(Config.DATA_DIR.glob("greeting_*.txt"))
        if not files:
            self.view.show_no_history()
            return
        files.sort(reverse=True)
        self.view.show_history(files)

    def _handle_batch_screening(self) -> None:
        """处理岗位库批量匹配流程。"""
        params = self.view.prompt_batch_screening()
        try:
            limit = int(params["limit_text"])
            threshold = float(params["threshold_text"])
        except ValueError:
            self.view.show_invalid_number()
            return
        self.job_screening_model.use_repository(JobRepository(params["db_path"]))
        self.job_screening_model.use_strategy(params["strategy_id"])
        results = self.job_screening_model.analyze_pending_jobs(
            limit=limit,
            threshold=threshold,
        )
        if not results:
            self.view.show_no_pending_jobs()
            return
        self.view.show_batch_results(results)

    def _handle_job_apply(self) -> None:
        """处理已入队岗位的自动投递流程。"""
        params = self.view.prompt_job_apply()
        try:
            limit = int(params["limit_text"])
        except ValueError:
            self.view.show_invalid_number()
            return
        request = JobApplyRequest(
            db_path=params["db_path"],
            limit=limit,
            require_login=params["require_login"],
            dry_run=params["dry_run"],
            fill_only=params["fill_only"],
            no_close_tab=params["no_close_tab"],
            greetings_dir=params["greetings_dir"],
            debug=_env_bool("BOSS_DEBUG", False),
        )
        asyncio.run(self.job_apply_model.apply_ready_jobs(request))

    def _handle_agent_flow(self) -> None:
        """处理抓取、匹配、入队、投递一体化主流程。"""
        params = self.view.prompt_agent_flow()
        try:
            target_apply_count = int(params["target_apply_count_text"])
            min_match_batch_size = int(params["min_match_batch_size_text"])
            screening_threshold = float(params["screening_threshold_text"])
        except ValueError:
            self.view.show_invalid_number()
            return

        request = JobApplicationAgentRequest(
            db_path=params["db_path"],
            target_apply_count=target_apply_count,
            min_match_batch_size=min(max(min_match_batch_size, 5), 10),
            strategy_id=params["strategy_id"],
            screening_threshold=screening_threshold,
            require_login=True,
            greetings_dir=params["greetings_dir"],
            debug=_env_bool("BOSS_DEBUG", False),
        )
        result = asyncio.run(self.job_application_agent.run(request))
        self.view.show_agent_flow_result(result)

    def _handle_rescore_queue(self) -> None:
        """按新阈值重算已分析岗位的入队状态。"""
        params = self.view.prompt_rescore_queue()
        try:
            threshold = float(params["threshold_text"])
            limit = int(params["limit_text"])
            apply_count = int(params["apply_count_text"])
        except ValueError:
            self.view.show_invalid_number()
            return
        if limit <= 0:
            return

        repository = JobRepository(params["db_path"])
        print(
            f"\n[agent] 开始按新阈值重算投递队列："
            f"目标阈值 {threshold:.1f}，本次最多重算 {limit} 个岗位。"
        )
        result = repository.recalculate_suitability_by_threshold(
            threshold=threshold,
            limit=limit,
        )
        print(
            f"[agent] 重算完成：已重算 {result['updated']} 个岗位，"
            f"新增/保留在投递队列 {result['queued']} 个，"
            f"跳过 {result['skipped']} 个。"
        )
        ready_count = repository.count_ready_to_apply_jobs()
        print(f"[agent] 当前待投递队列：{ready_count} 个。")
        self.view.show_rescore_result(result)
        if apply_count <= 0:
            return
        asyncio.run(
            self._run_rescore_apply_flow(
                repository=repository,
                db_path=params["db_path"],
                threshold=threshold,
                apply_count=apply_count,
                greetings_dir=params["greetings_dir"],
                initial_ready_count=ready_count,
            )
        )

    async def _run_rescore_apply_flow(
        self,
        *,
        repository: JobRepository,
        db_path: str,
        threshold: float,
        apply_count: int,
        greetings_dir: str,
        initial_ready_count: int,
    ) -> None:
        """执行菜单 7 的完整闭环：重投已有分数岗位，不足时补分析后继续投递。"""
        total_processed = 0
        total_sent = 0
        total_already_contacted = 0
        total_failed = 0
        ready_count = initial_ready_count
        debug = _env_bool("BOSS_DEBUG", False)
        strategy_id = os.getenv("BOSS_MATCH_STRATEGY", "backend_ai")
        browser = None

        async def apply_round(target_count: int, require_login: bool) -> None:
            nonlocal total_processed, total_sent, total_already_contacted, total_failed
            request = JobApplyRequest(
                db_path=db_path,
                limit=target_count,
                require_login=require_login,
                dry_run=False,
                fill_only=False,
                no_close_tab=False,
                greetings_dir=greetings_dir,
                debug=debug,
            )
            summary = await self.job_apply_model.apply_ready_jobs(request, browser=browser)
            total_processed += summary.processed_count
            total_sent += summary.sent_count
            total_already_contacted += summary.already_contacted_count
            total_failed += summary.failed_count
            print(
                f"[agent] 投递完成：本轮实际发送 {summary.sent_count} 个，"
                f"继续沟通/已沟通 {summary.already_contacted_count} 个，"
                f"发送失败 {summary.failed_count} 个。"
            )

        try:
            if ready_count > 0 or apply_count > 0:
                browser = await self.job_apply_model.apply_facade._start_browser()
                bootstrap_tab = await browser.get(_BOSS_ORIGIN, new_window=_env_bool("BOSS_NEW_WINDOW", False))
                await bootstrap_tab
                print(f"✓ 已打开: {bootstrap_tab.url}")
                print(">>> 浏览器已打开，请先手动完成登录。")
                await self.job_apply_model.apply_facade._ensure_manual_login(bootstrap_tab, debug=debug)

            if ready_count > 0:
                print(
                    f"\n[agent] 开始投递："
                    f"本轮目标实际发送 {min(apply_count, ready_count)} 个，待投递队列 {ready_count} 个。"
                )
                await apply_round(apply_count, require_login=False)

            remaining_apply_count = max(apply_count - total_sent, 0)
            while remaining_apply_count > 0:
                pending_count = repository.count_pending_jobs()
                if pending_count <= 0:
                    print(
                        f"[agent] 没有更多无历史分数的待分析岗位。"
                        f"本轮目标还差 {remaining_apply_count} 个，流程结束。"
                    )
                    break

                screening_limit = min(remaining_apply_count, pending_count)
                print(
                    f"\n[agent] 开始补充投递队列："
                    f"当前待发送 {remaining_apply_count} 个，待分析岗位 {pending_count} 个。"
                )
                self.job_screening_model.use_repository(repository)
                self.job_screening_model.use_strategy(strategy_id)
                screening_results = self.job_screening_model.analyze_pending_jobs(
                    limit=screening_limit,
                    threshold=threshold,
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

                await apply_round(remaining_apply_count, require_login=False)
                remaining_apply_count = max(apply_count - total_sent, 0)
        finally:
            if browser is not None:
                await self.job_apply_model.apply_facade._safe_close_browser(browser, debug=debug)

        self.view.show_apply_result(
            processed_count=total_processed,
            sent_count=total_sent,
            already_contacted_count=total_already_contacted,
            failed_count=total_failed,
        )
        if total_sent < apply_count:
            print(
                f"[agent] 完整流程结束：目标实际发送 {apply_count} 个，"
                f"当前完成 {total_sent} 个，剩余 {apply_count - total_sent} 个未完成。"
            )

    def _save_result(self, jd_info: dict, match_result: dict, greeting: str) -> Path:
        """把手动分析结果保存为本地文本记录。"""
        from datetime import datetime

        Config.ensure_dirs()
        filepath = Config.DATA_DIR / f"greeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filepath, "w", encoding="utf-8") as file:
            file.write("=" * 60 + "\n")
            file.write("职位信息\n")
            file.write("=" * 60 + "\n")
            file.write(f"职位: {jd_info['job_title']}\n")
            file.write(f"公司: {jd_info['company_name']}\n")
            file.write(f"薪资: {jd_info['salary_range']}\n")
            file.write(f"地点: {jd_info['location']}\n")
            file.write(f"链接: {jd_info['job_url']}\n\n")
            file.write("=" * 60 + "\n")
            file.write("匹配结果\n")
            file.write("=" * 60 + "\n")
            file.write(f"匹配度: {match_result['match_score']} ({match_result['match_level']})\n")
            file.write(f"推荐: {'是' if match_result['is_recommended'] else '否'}\n")
            file.write(f"分析: {match_result['analysis']}\n\n")
            file.write("=" * 60 + "\n")
            file.write("打招呼语\n")
            file.write("=" * 60 + "\n")
            file.write(greeting)
        return filepath
