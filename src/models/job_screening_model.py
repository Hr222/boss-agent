"""批量筛选模型：负责岗位库分析与匹配结果回写。"""

from dataclasses import dataclass
import re

from src.models.job_matching_model import JobMatchingModel
from src.models.job_repository import JobRepository


@dataclass(frozen=True)
class ScreeningJobResult:
    """单个岗位筛选结果。"""

    job_title: str
    job_url: str
    status: str
    reason: str = ""
    match_score: float = 0.0
    match_level: str = ""
    is_recommended: bool = False
    is_suitable: bool = False
    analysis: str = ""
    missing_skills: list[str] | None = None
    matched_skills: list[str] | None = None
    greeting_path: str = ""

class JobScreeningModel:
    """筛选待分析岗位并回写匹配结果。

    它负责“筛选用例”本身：取待分析岗位、调用匹配器、把结果写回岗位库。
    它不负责控制台展示，也不负责浏览器抓取。
    """

    def __init__(
        self,
        repository: JobRepository | None = None,
        matching_model: JobMatchingModel | None = None,
    ) -> None:
        """初始化岗位仓储与匹配模型。"""
        self.repository = repository or JobRepository()
        self.matching_model = matching_model or JobMatchingModel()

    def use_repository(self, repository: JobRepository) -> None:
        """切换当前使用的岗位仓储。"""
        self.repository = repository

    def use_strategy(self, strategy_id: str) -> None:
        """切换当前批量筛选使用的策略。"""
        self.matching_model.set_strategy(strategy_id)

    def use_llm_provider(self, provider: str) -> None:
        """切换当前批量筛选使用的 LLM 提供方。"""
        self.matching_model.set_llm_provider(provider)

    def analyze_pending_jobs(self, limit: int, threshold: float) -> list[ScreeningJobResult]:
        """批量分析未处理岗位。招呼语文件改为发送成功后再归档。"""
        results: list[ScreeningJobResult] = []
        pending_jobs = self.repository.get_pending_jobs(limit=limit)
        total_jobs = len(pending_jobs)

        for index, row in enumerate(pending_jobs, 1):
            job = self.repository.build_job_description(row)
            # 匹配阶段增加显式进度日志，避免长时间无输出让人误判程序假死。
            print(f"[screening] {index}/{total_jobs} 开始分析: {job.job_title} @ {job.company_name}")
            match_result = self.matching_model.analyze_match(job)
            if match_result is None:
                failure_reason = self.matching_model.last_failure_reason or "未知错误"
                if self.matching_model.last_failure_is_temporary:
                    defer_count = self.repository.mark_screening_deferred(job.job_url, failure_reason)
                    print(
                        f"[screening] {index}/{total_jobs} 暂缓分析: {job.job_title} | "
                        f"保留待分析，暂缓次数={defer_count}"
                    )
                    results.append(
                        ScreeningJobResult(
                            job_title=job.job_title,
                            job_url=job.job_url,
                            status="deferred",
                            reason=failure_reason,
                        )
                    )
                    continue
                print(f"[screening] {index}/{total_jobs} 分析失败: {job.job_title} | reason={failure_reason}")
                results.append(
                    ScreeningJobResult(
                        job_title=job.job_title,
                        job_url=job.job_url,
                        status="failed",
                        reason=failure_reason,
                    )
                )
                continue

            # suitability 既看分数，也看规则约束后的推荐结果。
            # 仓储层负责最终落库，因此这里把“分析结果”和“是否入队”统一收口。
            is_suitable = self.repository.save_match_result(job.job_url, match_result, threshold)
            reason = self._build_result_reason(match_result.analysis, match_result.missing_skills)
            print(
                f"[screening] {index}/{total_jobs} 完成: {job.job_title} | "
                f"score={match_result.match_score:.1f}({match_result.match_level}) | "
                f"recommended={match_result.is_recommended} | suitable={bool(is_suitable)} | "
                f"reason={reason}"
            )
            results.append(
                ScreeningJobResult(
                    job_title=job.job_title,
                    job_url=job.job_url,
                    status="ok",
                    match_score=match_result.match_score,
                    match_level=match_result.match_level,
                    is_recommended=match_result.is_recommended,
                    is_suitable=bool(is_suitable),
                    analysis=match_result.analysis,
                    missing_skills=match_result.missing_skills,
                    matched_skills=match_result.matched_skills,
                    greeting_path="",
                )
            )

        return results

    def _build_result_reason(self, analysis: str, missing_skills: list[str]) -> str:
        """构造简短原因文本，便于控制台快速判断为何未入队。"""
        analysis_text = re.sub(r"\s+", " ", (analysis or "")).strip()
        if missing_skills:
            skills_text = ", ".join(missing_skills[:4])
            if analysis_text:
                return f"{analysis_text[:80]} | 缺口: {skills_text}"
            return f"缺口: {skills_text}"
        return analysis_text[:120] if analysis_text else "无明显缺口"


__all__ = ["JobScreeningModel", "ScreeningJobResult"]
