"""控制台控制器：负责把用户输入路由到对应模型。"""

import asyncio
from pathlib import Path

from src.config.settings import Config
from src.infrastructure.browser.nodriver_runtime import _env_bool
from src.models.job_apply_model import JobApplyModel, JobApplyRequest
from src.models.job_agent_flow_model import JobAgentFlowModel, JobAgentFlowRequest
from src.models.job_repository import JobRepository
from src.models.job_screening_model import JobScreeningModel
from src.models.manual_job_model import ManualJobModel
from src.models.resume_profile import ResumeProfile
from src.models.resume_store import ResumeStore
from src.views.console_view import ConsoleView


class ConsoleController:
    """协调 View 与 Model 的主控制器。"""

    def __init__(
        self,
        view: ConsoleView | None = None,
        resume_store: ResumeStore | None = None,
        manual_job_model: ManualJobModel | None = None,
        job_screening_model: JobScreeningModel | None = None,
        job_apply_model: JobApplyModel | None = None,
        job_agent_flow_model: JobAgentFlowModel | None = None,
    ) -> None:
        self.view = view or ConsoleView()
        self.resume_store = resume_store or ResumeStore()
        self.manual_job_model = manual_job_model or ManualJobModel()
        self.job_screening_model = job_screening_model or JobScreeningModel()
        self.job_apply_model = job_apply_model or JobApplyModel()
        self.job_agent_flow_model = job_agent_flow_model or JobAgentFlowModel()

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
        # 允许用户在控制台里切换当前使用的岗位库。
        self.job_screening_model.use_repository(JobRepository(params["db_path"]))
        self.job_screening_model.use_strategy(params["strategy_id"])
        results = self.job_screening_model.analyze_pending_jobs(
            limit=limit,
            threshold=threshold,
            out_dir=params["out_dir"],
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

        request = JobAgentFlowRequest(
            db_path=params["db_path"],
            target_apply_count=target_apply_count,
            min_match_batch_size=min(max(min_match_batch_size, 5), 10),
            strategy_id=params["strategy_id"],
            screening_threshold=screening_threshold,
            require_login=True,
            greetings_dir=params["greetings_dir"],
            debug=_env_bool("BOSS_DEBUG", False),
        )
        result = asyncio.run(self.job_agent_flow_model.run(request))
        self.view.show_agent_flow_result(result)

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
