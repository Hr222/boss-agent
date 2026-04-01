"""职位仓储：对 SQLite 中的岗位数据提供统一访问接口。"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models.job_description import JobDescription
from src.models.job_match_result import JobMatchResult
from src.infrastructure.persistence.sqlite_job_store import JobRecord, SQLiteJobStore


class SQLiteJobRepository:
    """对岗位数据的读写做一层封装，避免业务逻辑直接操作 SQL 行对象。"""

    def __init__(self, db_path: str | Path = "data/boss_jobs.sqlite3") -> None:
        self.sqlite = SQLiteJobStore(db_path)

    def save_links(self, job_urls: list[str], keyword: str, city: str) -> int:
        """保存抓取到的岗位链接。"""
        return self.sqlite.upsert_links(job_urls, keyword=keyword, city=city)

    def save_jobs(self, jobs: list[JobRecord]) -> int:
        """批量保存岗位信息，仅统计实际写入次数。"""
        wrote = 0
        for job in jobs:
            if self.sqlite.upsert_job_if_changed(job):
                wrote += 1
        return wrote

    def get_job_store_stats(self) -> dict[str, int]:
        """返回岗位库中的基础统计，便于脚本或 demo 做落库校验。"""
        self.sqlite.init()
        with self.sqlite._connect() as conn:
            jobs_total = self._query_count(conn, "SELECT COUNT(*) FROM jobs")
            links_total = self._query_count(conn, "SELECT COUNT(*) FROM job_links")
            jobs_with_jd = self._query_count(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE jd IS NOT NULL AND TRIM(jd) != ''",
            )
        return {
            "jobs_total": jobs_total,
            "links_total": links_total,
            "jobs_with_jd": jobs_with_jd,
        }

    def get_recent_jobs(self, limit: int = 5) -> list[dict[str, Any]]:
        """读取最近写入的岗位摘要，便于人工快速确认落库内容。"""
        self.sqlite.init()
        with self.sqlite._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_url, title, company, salary, city, captured_at
                FROM jobs
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_jobs_with_jd(self, limit: int = 10) -> list[dict[str, Any]]:
        """读取最近落库且带 JD 内容的岗位，用于匹配 demo 或手工核查。"""
        self.sqlite.init()
        with self.sqlite._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE jd IS NOT NULL AND TRIM(jd) != ''
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_pending_jobs(self, limit: int) -> list[dict[str, Any]]:
        """读取待匹配岗位。"""
        return [dict(row) for row in self.sqlite.iter_pending_jobs(limit=limit)]

    def count_pending_jobs(self) -> int:
        """统计当前待匹配岗位数量。"""
        return self.sqlite.count_pending_jobs()

    def get_ready_to_apply_jobs(self, limit: int) -> list[dict[str, Any]]:
        """读取已判定适合、但尚未投递的岗位。"""
        fetch_limit = max(int(limit) * 5, 50)
        rows = [dict(row) for row in self.sqlite.iter_ready_to_apply(limit=fetch_limit)]
        max_failures = self._get_apply_failure_limit()
        ready_rows = [row for row in rows if self._get_apply_fail_count(row) < max_failures]
        return ready_rows[: max(int(limit), 0)]

    def count_ready_to_apply_jobs(self) -> int:
        """统计已入投递队列、但尚未投递的岗位数量。"""
        rows = [dict(row) for row in self.sqlite.iter_ready_to_apply(limit=10000)]
        max_failures = self._get_apply_failure_limit()
        return sum(1 for row in rows if self._get_apply_fail_count(row) < max_failures)

    def recalculate_suitability_by_threshold(
        self,
        threshold: float,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """按新阈值重算已分析且未投递岗位的入队状态。"""
        self.sqlite.init()
        sql = """
            SELECT job_url, title, company, raw_json
            FROM jobs
            WHERE (is_applied IS NULL OR is_applied = 0)
            ORDER BY captured_at DESC
        """
        params: tuple[Any, ...] = ()
        updated = 0
        queued = 0
        skipped = 0
        below_threshold = 0
        details: list[dict[str, Any]] = []
        with self.sqlite._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        for row in rows:
            payload = self._load_raw_json(row["raw_json"])
            title = str(row["title"] or row["job_url"] or "").strip()
            company = str(row["company"] or "").strip()
            if "match_score" not in payload:
                skipped += 1
                continue
            try:
                match_score = float(payload.get("match_score", 0) or 0)
            except Exception:
                skipped += 1
                continue

            if match_score < float(threshold):
                self.sqlite.set_job_flags(str(row["job_url"]), is_suitable=0)
                self.sqlite.update_raw_json(
                    str(row["job_url"]),
                    {
                        "match_threshold": threshold,
                        "final_suitability": 0,
                    },
                )
                below_threshold += 1
                continue

            if limit is not None and int(limit) > 0 and updated >= int(limit):
                self.sqlite.set_job_flags(str(row["job_url"]), is_suitable=0)
                self.sqlite.update_raw_json(
                    str(row["job_url"]),
                    {
                        "match_threshold": threshold,
                        "final_suitability": 0,
                    },
                )
                continue

            is_suitable = 1
            self.sqlite.set_job_flags(str(row["job_url"]), is_suitable=is_suitable)
            self.sqlite.update_raw_json(
                str(row["job_url"]),
                {
                    "match_threshold": threshold,
                    "final_suitability": is_suitable,
                },
            )
            updated += 1
            queued += is_suitable
            details.append(
                {
                    "job_title": title,
                    "company_name": company,
                    "match_score": match_score,
                    "is_suitable": bool(is_suitable),
                    "status": "updated",
                    "reason": "达到阈值",
                }
            )

        return {
            "updated": updated,
            "queued": queued,
            "skipped": skipped,
            "below_threshold": below_threshold,
            "details": details,
        }

    def save_match_result(
        self,
        job_url: str,
        match_result: JobMatchResult,
        threshold: float,
    ) -> int:
        """保存匹配结果，并返回最终 suitability 状态。"""
        # 入队阈值以用户本次运行输入为准，不再额外受 is_recommended 限制。
        is_suitable = 1 if float(match_result.match_score) >= float(threshold) else 0
        self.sqlite.set_job_flags(job_url, is_suitable=is_suitable)
        self.sqlite.update_raw_json(
            job_url,
            {
                "match_score": match_result.match_score,
                "match_level": match_result.match_level,
                "match_threshold": threshold,
                "final_suitability": is_suitable,
                "greeting_message": match_result.greeting_message,
                "matched_skills": match_result.matched_skills,
                "missing_skills": match_result.missing_skills,
                "analysis": match_result.analysis,
                "is_recommended": match_result.is_recommended,
            },
        )
        return is_suitable

    def mark_applied(self, job_url: str) -> None:
        """标记岗位已投递。"""
        self.sqlite.set_job_flags(job_url, is_applied=1)
        self.sqlite.update_raw_json(
            job_url,
            {
                "last_applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "apply_fail_count": 0,
                "last_apply_failure_reason": "",
            },
        )

    def mark_apply_failed(self, job_url: str, reason: str = "") -> int:
        """累计岗位投递失败次数，并返回当前失败总次数。"""
        self.sqlite.init()
        row = self.sqlite.get_job_row(job_url)
        payload = dict(row) if row else {"job_url": job_url}
        next_fail_count = self._get_apply_fail_count(payload) + 1
        patch = {
            "apply_fail_count": next_fail_count,
            "last_apply_failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if reason:
            patch["last_apply_failure_reason"] = reason
        self.sqlite.update_raw_json(job_url, patch)
        return next_fail_count

    def build_job_description(self, row: dict[str, Any]) -> JobDescription:
        """把数据库记录转换为业务层使用的 JobDescription。"""
        job_url = str(row.get("job_url") or "").strip()
        jd_text = self._clean_jd_text(str(row.get("jd") or "").strip())
        return JobDescription(
            job_id=self._parse_job_id(job_url),
            job_title=str(row.get("title") or ""),
            company_name=str(row.get("company") or ""),
            salary_range=str(row.get("salary") or ""),
            location=str(row.get("city") or ""),
            job_requirements=jd_text,
            job_description=jd_text,
            tags=self._load_tags(row.get("tags_json")),
            job_url=job_url,
        )

    @staticmethod
    def _parse_job_id(job_url: str) -> str:
        """从 BOSS 职位链接中提取 job_id。"""
        import re

        match = re.search(r"/job_detail/([^/?]+)\.html", job_url)
        return match.group(1) if match else job_url

    @staticmethod
    def _load_tags(tags_json: Any) -> list[str]:
        """把数据库中的 tags_json 解析成字符串列表。"""
        if not tags_json:
            return []
        try:
            value = json.loads(tags_json)
        except Exception:
            return []
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _query_count(conn: sqlite3.Connection, sql: str) -> int:
        """执行 count 查询并返回整数结果。"""
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _get_apply_failure_limit() -> int:
        """达到失败阈值的岗位将不再进入自动投递队列。"""
        return max(int(os.getenv("BOSS_APPLY_MAX_FAILURES", "3")), 1)

    @staticmethod
    def _get_apply_fail_count(row: dict[str, Any]) -> int:
        """从 raw_json 中提取累计投递失败次数。"""
        raw_json = row.get("raw_json")
        if not raw_json:
            return 0
        payload = SQLiteJobRepository._load_raw_json(raw_json)
        try:
            return max(int(payload.get("apply_fail_count", 0)), 0)
        except Exception:
            return 0

    @staticmethod
    def _load_raw_json(raw_json: Any) -> dict[str, Any]:
        """把 raw_json 尽量安全地解析为字典。"""
        try:
            payload = json.loads(raw_json) or {}
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _clean_jd_text(text: str) -> str:
        """清洗 Boss 页面里混入的样式、站点字样与噪音字符。"""
        import re

        cleaned = text or ""
        cleaned = re.sub(r"\.[A-Za-z0-9_-]+\{[^}]*\}", " ", cleaned)
        cleaned = re.sub(r"[A-Za-z0-9_-]+\{[^}]*\}", " ", cleaned)
        cleaned = re.sub(r"(BOSS直聘|直聘|boss|kanzhun|来自BOSS直聘)", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s*([：:；;，,。])\s*", r"\1", cleaned)
        return cleaned.strip()
