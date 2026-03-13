"""批量筛选模型：负责岗位库分析与匹配结果回写。"""

import re
from pathlib import Path

from src.models.job_matching_model import JobMatchingModel
from src.models.job_repository import JobRepository


class JobScreeningModel:
    """筛选待分析岗位并回写匹配结果。"""

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

    def analyze_pending_jobs(self, limit: int, threshold: float, out_dir: str | Path) -> list[dict]:
        """批量分析未处理岗位。招呼语文件改为发送成功后再归档。"""
        results: list[dict] = []
        pending_jobs = self.repository.get_pending_jobs(limit=limit)
        total_jobs = len(pending_jobs)

        for index, row in enumerate(pending_jobs, 1):
            job = self.repository.build_job_description(row)
            # 匹配阶段增加显式进度日志，避免长时间无输出让人误判程序假死。
            print(f"[screening] {index}/{total_jobs} 开始分析: {job.job_title} @ {job.company_name}")
            match_result = self.matching_model.analyze_match(job)
            if match_result is None:
                print(f"[screening] {index}/{total_jobs} 分析失败: {job.job_title}")
                results.append(
                    {
                        "job_title": job.job_title,
                        "job_url": job.job_url,
                        "status": "failed",
                    }
                )
                continue

            # suitability 既看分数，也看规则约束后的推荐结果。
            is_suitable = self.repository.save_match_result(job.job_url, match_result, threshold)
            reason = self._build_result_reason(match_result.analysis, match_result.missing_skills)
            print(
                f"[screening] {index}/{total_jobs} 完成: {job.job_title} | "
                f"score={match_result.match_score:.1f}({match_result.match_level}) | "
                f"recommended={match_result.is_recommended} | suitable={bool(is_suitable)} | "
                f"reason={reason}"
            )
            results.append(
                {
                    "job_title": job.job_title,
                    "job_url": job.job_url,
                    "status": "ok",
                    "match_score": match_result.match_score,
                    "match_level": match_result.match_level,
                    "is_recommended": match_result.is_recommended,
                    "is_suitable": is_suitable,
                    "analysis": match_result.analysis,
                    "missing_skills": match_result.missing_skills,
                    "matched_skills": match_result.matched_skills,
                    "greeting_path": "",
                }
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


__all__ = ["JobScreeningModel"]
