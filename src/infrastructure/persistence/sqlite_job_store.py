"""SQLite 原子存储层：负责最底层 jobs / job_links 表操作。"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from src.config.settings import Config


def _utc_now_iso() -> str:
    """生成 UTC ISO 时间戳，统一用于落库。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class JobRecord:
    """抓取阶段使用的原始岗位记录。"""

    job_url: str
    title: str = ""
    salary: str = ""
    city: str = ""
    experience: str = ""
    education: str = ""
    company: str = ""
    tags: tuple[str, ...] = ()
    jd: str = ""
    source: str = "nodriver"
    captured_at: str = ""
    raw: Optional[dict[str, Any]] = None

    def to_db_params(self) -> dict[str, Any]:
        """转换为适合直接写入 SQLite 的参数结构。"""
        payload = asdict(self)
        payload["tags_json"] = json.dumps(list(self.tags), ensure_ascii=False)
        payload["raw_json"] = json.dumps(self.raw or {}, ensure_ascii=False)
        payload["captured_at"] = self.captured_at or _utc_now_iso()
        payload.pop("tags")
        payload.pop("raw")
        return payload


class SQLiteJobStore:
    """封装底层 SQLite 表结构与原子更新逻辑。"""

    def __init__(self, db_path: str | Path = "data/boss_jobs.sqlite3") -> None:
        self.db_path = Config.resolve_project_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """创建数据库连接，并把结果行设置为可按列名访问。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        """初始化 jobs / job_links 表，并执行轻量迁移。"""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_url TEXT PRIMARY KEY,
                    title TEXT,
                    salary TEXT,
                    city TEXT,
                    experience TEXT,
                    education TEXT,
                    company TEXT,
                    tags_json TEXT,
                    jd TEXT,
                    is_suitable INTEGER,
                    is_applied INTEGER,
                    source TEXT,
                    captured_at TEXT,
                    raw_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_links (
                    job_url TEXT PRIMARY KEY,
                    keyword TEXT,
                    city TEXT,
                    collected_at TEXT
                )
                """
            )
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """为老库补充缺失列。"""
        jobs_cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "is_suitable" not in jobs_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN is_suitable INTEGER")
        if "is_applied" not in jobs_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN is_applied INTEGER")

    def upsert_job(self, job: JobRecord) -> None:
        """全量 upsert 一条岗位记录。"""
        self.init()
        params = job.to_db_params()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_url, title, salary, city, experience, education, company,
                    tags_json, jd, is_suitable, is_applied, source, captured_at, raw_json
                ) VALUES (
                    :job_url, :title, :salary, :city, :experience, :education, :company,
                    :tags_json, :jd, NULL, NULL, :source, :captured_at, :raw_json
                )
                ON CONFLICT(job_url) DO UPDATE SET
                    title=excluded.title,
                    salary=excluded.salary,
                    city=excluded.city,
                    experience=excluded.experience,
                    education=excluded.education,
                    company=excluded.company,
                    tags_json=excluded.tags_json,
                    jd=excluded.jd,
                    source=excluded.source,
                    captured_at=excluded.captured_at,
                    raw_json=excluded.raw_json
                """
            )

    def upsert_job_if_changed(self, job: JobRecord) -> bool:
        """
        仅在抓取字段发生变化时更新岗位，且保留人工/流程维护的状态字段。
        """
        self.init()
        params = job.to_db_params()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_url = ?", (job.job_url,)).fetchone()
            if row is not None:
                existing = dict(row)
                # 只比较抓取相关字段，避免每次抓取都写库。
                same = (
                    (existing.get("title") or "") == params["title"]
                    and (existing.get("salary") or "") == params["salary"]
                    and (existing.get("city") or "") == params["city"]
                    and (existing.get("experience") or "") == params["experience"]
                    and (existing.get("education") or "") == params["education"]
                    and (existing.get("company") or "") == params["company"]
                    and (existing.get("tags_json") or "") == params["tags_json"]
                    and (existing.get("jd") or "") == params["jd"]
                    and (existing.get("raw_json") or "") == params["raw_json"]
                    and (existing.get("source") or "") == params["source"]
                )
                if same:
                    return False

                conn.execute(
                    """
                    UPDATE jobs SET
                        title=:title,
                        salary=:salary,
                        city=:city,
                        experience=:experience,
                        education=:education,
                        company=:company,
                        tags_json=:tags_json,
                        jd=:jd,
                        source=:source,
                        captured_at=:captured_at,
                        raw_json=:raw_json
                    WHERE job_url=:job_url
                    """,
                    params,
                )
                return True

            conn.execute(
                """
                INSERT INTO jobs (
                    job_url, title, salary, city, experience, education, company,
                    tags_json, jd, is_suitable, is_applied, source, captured_at, raw_json
                ) VALUES (
                    :job_url, :title, :salary, :city, :experience, :education, :company,
                    :tags_json, :jd, NULL, NULL, :source, :captured_at, :raw_json
                )
                """,
                params,
            )
            return True

    def upsert_links(self, job_urls: Iterable[str], keyword: str, city: str) -> int:
        """写入岗位链接表，仅统计新增数量。"""
        self.init()
        now = _utc_now_iso()
        rows = [(u, keyword, city, now) for u in job_urls if u]
        if not rows:
            return 0
        with self._connect() as conn:
            before_changes = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO job_links (job_url, keyword, city, collected_at)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            inserted = conn.total_changes - before_changes
        return int(inserted or 0)

    def iter_pending_jobs(self, limit: int = 20) -> list[sqlite3.Row]:
        """读取已有 JD 且尚未标记 suitability 的岗位。"""
        self.init()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE (is_suitable IS NULL) AND (jd IS NOT NULL) AND (TRIM(jd) != '')
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return list(rows)

    def count_pending_jobs(self) -> int:
        """统计当前库中待匹配岗位数量。"""
        self.init()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM jobs
                WHERE (is_suitable IS NULL) AND (jd IS NOT NULL) AND (TRIM(jd) != '')
                """
            ).fetchone()
        return int(row[0]) if row else 0

    def iter_ready_to_apply(self, limit: int = 15) -> list[sqlite3.Row]:
        """读取已判定适合、但尚未投递的岗位。"""
        self.init()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE (is_suitable = 1) AND (is_applied IS NULL OR is_applied = 0)
                ORDER BY captured_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return list(rows)

    def set_job_flags(
        self,
        job_url: str,
        *,
        is_suitable: int | None = None,
        is_applied: int | None = None,
    ) -> None:
        """按需更新岗位状态位。"""
        self.init()
        updates: list[str] = []
        params: dict[str, Any] = {"job_url": job_url}
        if is_suitable is not None:
            updates.append("is_suitable = :is_suitable")
            params["is_suitable"] = int(is_suitable)
        if is_applied is not None:
            updates.append("is_applied = :is_applied")
            params["is_applied"] = int(is_applied)
        if not updates:
            return
        with self._connect() as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE job_url = :job_url",
                params,
            )

    def update_raw_json(self, job_url: str, patch: dict[str, Any]) -> None:
        """合并更新 jobs.raw_json，保留已有字段。"""
        self.init()
        with self._connect() as conn:
            row = conn.execute("SELECT raw_json FROM jobs WHERE job_url = ?", (job_url,)).fetchone()
            existing = {}
            if row and row["raw_json"]:
                try:
                    existing = json.loads(row["raw_json"]) or {}
                except Exception:
                    existing = {}
            existing.update(patch or {})
            conn.execute(
                "UPDATE jobs SET raw_json = ? WHERE job_url = ?",
                (json.dumps(existing, ensure_ascii=False), job_url),
            )
