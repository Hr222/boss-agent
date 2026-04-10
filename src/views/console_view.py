"""控制台视图：负责所有 CLI 展示与输入采集。"""

from pathlib import Path

from src.config.settings import Config
from src.models.job_application_agent import AgentRunSummary
from src.models.job_screening_model import ScreeningJobResult
from src.models.resume_profile import ResumeProfile
from src.models.strategies.strategy_factory import StrategyFactory
from src.views.console_prompts import collect_manual_job_input, print_banner


class ConsoleView:
    """封装控制台输入输出。"""

    def show_banner(self) -> None:
        """显示启动横幅。"""
        print_banner()

    def show_current_resume(self, resume: ResumeProfile) -> None:
        """展示当前加载的简历摘要。"""
        print(f"\n当前简历: {resume.name} | {resume.target_position}")

    def show_current_llm_provider(self, provider: str) -> None:
        """展示当前会话选择的 LLM 提供方。"""
        provider_text = "DeepSeek" if provider == "deepseek" else "智谱 / Z.ai"
        print(f"当前 LLM: {provider_text}")

    def get_main_menu_choice(self) -> str:
        """展示主菜单并读取选择。"""
        print("\n" + "=" * 60)
        print("请选择操作")
        print("=" * 60)
        print("1. 输入JD生成打招呼语")
        print("2. 查看/更新简历")
        print("3. 查看历史记录")
        print("4. 批量分析岗位库")
        print("5. 自动投递已入队岗位")
        print("6. 运行闭环求职 Agent")
        print("7. 按新分数重算入队状态")
        print("0. 退出")
        return input("\n请选择 (0-7): ").strip()

    def show_goodbye(self) -> None:
        print("\n👋 再见！祝求职顺利！")

    def show_invalid_choice(self) -> None:
        print("\n无效的选择")

    def collect_manual_job(self) -> dict:
        """采集手动输入的岗位信息。"""
        return collect_manual_job_input()

    def show_empty_job_description(self) -> None:
        print("\n⚠️  职位描述为空，跳过")

    def show_manual_job_start(self, jd_info: dict) -> None:
        print(f"\n正在分析JD: {jd_info['job_title']} @ {jd_info['company_name']}")
        print("\n正在调用LLM分析匹配度并生成打招呼语...")

    def prompt_strategy_selection(self, default_strategy_id: str = "backend_ai") -> str:
        """采集当前分析流程所使用的岗位策略。"""
        print("\n请选择匹配策略")
        options = StrategyFactory.options()
        option_map = {str(index): strategy_id for index, (strategy_id, _) in enumerate(options, 1)}
        default_index = "1"
        for index, (strategy_id, display_name) in enumerate(options, 1):
            suffix = " (默认)" if strategy_id == default_strategy_id else ""
            if strategy_id == default_strategy_id:
                default_index = str(index)
            print(f"{index}. {display_name}{suffix}")
        selected = input(f"策略编号(默认 {default_index}): ").strip() or default_index
        return option_map.get(selected, default_strategy_id)

    def prompt_llm_provider(self, default_provider: str | None = None) -> str:
        """采集当前流程使用的 LLM 提供方。"""
        provider = (default_provider or Config.get_llm_provider()).strip().lower()
        option_map = {"1": "zhipu", "2": "deepseek"}
        default_index = "2" if provider == "deepseek" else "1"
        print("\n请选择 LLM 提供方")
        print(f"1. 智谱 / Z.ai{' (默认)' if default_index == '1' else ''}")
        print(f"2. DeepSeek{' (默认)' if default_index == '2' else ''}")
        selected = input(f"提供方编号(默认 {default_index}): ").strip() or default_index
        return option_map.get(selected, provider)

    def show_manual_job_failed(self) -> None:
        print("\n⚠️  LLM匹配分析失败，跳过")

    def show_manual_match_result(self, result) -> None:
        """展示单岗位分析结果与生成的招呼语。"""
        print("\n" + "=" * 60)
        print("匹配分析结果")
        print("=" * 60)
        print(f"匹配度: {result.match_score:.1f}分 ({result.match_level})")
        print(f"推荐投递: {'是' if result.is_recommended else '否'}")
        if result.matched_skills:
            print(f"匹配技能: {', '.join(result.matched_skills)}")
        if result.missing_skills:
            print(f"缺失技能: {', '.join(result.missing_skills)}")
        if result.analysis:
            print(f"分析: {result.analysis}")
        print("\n" + "=" * 60)
        print("生成的打招呼语")
        print("=" * 60)
        print(result.greeting_message)
        print("=" * 60)

    def confirm_save_result(self) -> bool:
        return input("\n是否保存? (y/n): ").strip().lower() == "y"

    def show_saved_result(self, filepath: Path) -> None:
        print(f"\n✅ 已保存到: {filepath}")

    def prompt_resume_action(self) -> str:
        return input("查看(v) or更新(u)简历? ").strip().lower()

    def show_resume_summary(self, resume: ResumeProfile) -> None:
        print(f"\n当前简历: {resume.name}")
        print(f"目标职位: {resume.target_position}")
        print(f"核心技能: {', '.join(resume.skills[:10])}")

    def show_create_resume_header(self) -> None:
        print("\n" + "=" * 60)
        print("创建简历")
        print("=" * 60)

    def collect_resume_fields(self) -> dict:
        """采集简历创建/更新所需字段。"""
        self.show_create_resume_header()
        name = input("姓名: ").strip()
        phone = input("手机: ").strip()
        email = input("邮箱: ").strip()
        target_position = input("目标职位: ").strip()
        target_salary = input("期望薪资: ").strip()
        target_location = input("期望地点: ").strip()
        years_of_experience = input("工作年限: ").strip()
        print("\n技能 (用逗号分隔):")
        skills = [s.strip() for s in input().split(",")]
        print("\n个人优势 (每行一个，空行结束):")
        advantages = []
        while True:
            advantage = input("优势: ")
            if not advantage:
                break
            advantages.append(advantage)
        return {
            "name": name,
            "phone": phone,
            "email": email,
            "target_position": target_position,
            "target_salary": target_salary,
            "target_location": target_location,
            "years_of_experience": years_of_experience,
            "skills": skills,
            "advantages": advantages,
        }

    def show_resume_saved(self) -> None:
        print("\n✅ 简历保存成功！")

    def show_no_history(self) -> None:
        print("\n暂无历史记录")

    def show_history(self, files: list[Path]) -> None:
        """展示历史生成文件列表。"""
        print(f"\n找到 {len(files)} 条记录 (最新10条):")
        for index, file in enumerate(files[:10], 1):
            print(f"  {index}. {file.name}")

    def prompt_batch_screening(self) -> dict:
        """采集批量筛选所需参数。"""
        print("\n" + "=" * 60)
        print("批量分析岗位库")
        print("=" * 60)
        return {
            "db_path": input("岗位库路径(默认 data/boss_jobs.sqlite3): ").strip() or "data/boss_jobs.sqlite3",
            "strategy_id": self.prompt_strategy_selection(),
            "limit_text": input("本次分析数量(默认 10): ").strip() or "10",
            "threshold_text": input("最低通过分数(默认 75): ").strip() or "75",
        }

    def show_invalid_number(self) -> None:
        print("\n⚠️  数量或分数格式无效")

    def show_no_pending_jobs(self) -> None:
        print("\n暂无待分析岗位（要求 jd 非空且 is_suitable 为空）。")

    def show_batch_results(self, results: list[ScreeningJobResult]) -> None:
        """展示批量筛选汇总结果。"""
        print("\n" + "=" * 60)
        print("批量分析结果")
        print("=" * 60)
        ok_count = 0
        deferred_count = 0
        suitable_count = 0
        for index, item in enumerate(results, 1):
            if item.status == "deferred":
                deferred_count += 1
                print(f"{index}. {item.job_title or item.job_url} | 暂缓分析，保留待分析")
                continue
            if item.status != "ok":
                print(f"{index}. {item.job_title or item.job_url} | 分析失败")
                continue
            ok_count += 1
            suitable_count += int(item.is_suitable)
            print(
                f"{index}. {item.job_title} | "
                f"匹配度={item.match_score:.1f}({item.match_level}) | "
                f"推荐={'是' if item.is_recommended else '否'} | "
                f"入投递队列={'是' if item.is_suitable else '否'}"
            )
        print("\n汇总")
        print(f"成功分析: {ok_count}/{len(results)}")
        print(f"暂缓分析: {deferred_count}/{len(results)}")
        print(f"进入投递队列: {suitable_count}/{len(results)}")

    def prompt_job_apply(self) -> dict:
        """采集自动投递所需参数。"""
        print("\n" + "=" * 60)
        print("自动投递已入队岗位")
        print("=" * 60)
        return {
            "db_path": input("岗位库路径(默认 data/boss_jobs.sqlite3): ").strip() or "data/boss_jobs.sqlite3",
            "limit_text": input("本次投递数量(默认 15): ").strip() or "15",
            "dry_run": input("仅定位不发送? (y/N): ").strip().lower() == "y",
            "fill_only": input("只填充输入框不发送? (y/N): ").strip().lower() == "y",
            "no_close_tab": input("保留岗位标签页? (y/N): ").strip().lower() == "y",
            "require_login": input("开始前等待手动登录? (Y/n): ").strip().lower() != "n",
            "greetings_dir": input("招呼语目录(默认 data/greetings): ").strip() or "data/greetings",
        }

    def prompt_agent_flow(self) -> dict:
        """采集闭环 Agent 所需参数。"""
        print("\n" + "=" * 60)
        print("闭环求职 Agent")
        print("=" * 60)
        return {
            "db_path": input("岗位库路径(默认 data/boss_jobs.sqlite3): ").strip() or "data/boss_jobs.sqlite3",
            "strategy_id": self.prompt_strategy_selection(),
            "target_apply_count_text": input("目标实际投递数量(默认 15): ").strip() or "15",
            "min_match_batch_size_text": input("每轮最小匹配数量(默认 5，范围 5-10): ").strip() or "5",
            "screening_threshold_text": input("最低通过分数(默认 75): ").strip() or "75",
            "greetings_dir": input("招呼语输出目录(默认 data/greetings): ").strip() or "data/greetings",
        }

    def prompt_rescore_queue(self) -> dict:
        """采集按新阈值重算入队状态所需参数。"""
        print("\n" + "=" * 60)
        print("按新分数重算入队状态")
        print("=" * 60)
        return {
            "db_path": input("岗位库路径(默认 data/boss_jobs.sqlite3): ").strip() or "data/boss_jobs.sqlite3",
            "threshold_text": input("新的最低通过分数(默认 75): ").strip() or "75",
            "limit_text": input("本次最多重算多少条(默认 15，输入 0 表示不执行): ").strip() or "15",
            "apply_count_text": input("本次重算后直接投递多少个(默认 15，输入 0 表示只重算不投递): ").strip() or "15",
            "greetings_dir": input("招呼语目录(默认 data/greetings): ").strip() or "data/greetings",
        }

    def show_rescore_result(self, result: dict[str, object]) -> None:
        """展示按阈值重算入队状态后的结果。"""
        print("\n" + "=" * 60)
        print("重算结果")
        print("=" * 60)
        print(f"已重算: {result['updated']}")
        print(f"重算后在投递队列: {result['queued']}")
        print(f"低于阈值未入队: {result.get('below_threshold', 0)}")
        print(f"跳过(无有效分数): {result['skipped']}")
        details = list(result.get("details", []) or [])
        if not details:
            return
        print("\n入队明细")
        for index, item in enumerate(details, 1):
            company = f" @ {item['company_name']}" if item.get("company_name") else ""
            score = "-" if item.get("match_score") is None else f"{float(item['match_score']):.1f}"
            queued_text = "是" if item.get("is_suitable") else "否"
            print(
                f"{index}. {item['job_title']}{company} | "
                f"score={score} | 入队={queued_text} | 原因={item['reason']}"
            )

    def show_apply_result(self, processed_count: int, sent_count: int, already_contacted_count: int, failed_count: int) -> None:
        """展示本轮投递汇总。"""
        print("\n" + "=" * 60)
        print("投递结果")
        print("=" * 60)
        print(f"本轮处理: {processed_count}")
        print(f"实际发送: {sent_count}")
        print(f"继续沟通/已沟通: {already_contacted_count}")
        print(f"发送失败: {failed_count}")

    def show_agent_flow_result(self, result: AgentRunSummary) -> None:
        """展示闭环 Agent 的最终执行结果。"""
        print("\n" + "=" * 60)
        print("闭环 Agent 结果")
        print("=" * 60)
        print(f"状态: {result.status}")
        print(f"目标实际投递: {result.target_apply_count}")
        print(f"累计实际投递: {result.sent_count}")
        print(f"继续沟通/已沟通: {result.already_contacted_count}")
        print(f"剩余待投递队列: {result.ready_count}")
