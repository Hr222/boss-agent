"""已入队岗位投递命令入口。"""

import argparse
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from src.infrastructure.browser.nodriver_runtime import _env_bool, run_async_entrypoint
from src.models.job_apply_model import JobApplyModel, JobApplyRequest
from src.models.job_repository import JobRepository


async def main() -> None:
    """解析命令行参数并执行浏览器投递。"""
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Send greeting messages to HR on BOSS using nodriver.")
    parser.add_argument("--db", default="data/boss_jobs.sqlite3")
    parser.add_argument("--limit", type=int, default=int(os.getenv("BOSS_APPLY_LIMIT", "15")))
    parser.add_argument("--job-url", help="Only preview/apply a specific job URL.")
    parser.add_argument("--greeting-file", help="Load greeting text from a file for single-job preview.")
    parser.add_argument("--greeting-text", help="Use the given greeting text directly for single-job preview.")
    parser.add_argument("--require-login", action="store_true", help="Wait for you to login manually before applying.")
    parser.add_argument("--dry-run", action="store_true", help="Open pages and locate inputs, but don't send or update DB.")
    parser.add_argument("--fill-only", action="store_true", help="Fill greeting into the input box but do not send.")
    parser.add_argument("--greetings-dir", default=os.getenv("BOSS_GREETINGS_DIR", "data/greetings"))
    parser.add_argument("--no-close-tab", action="store_true", help="Do not close tabs (for debugging).")
    args = parser.parse_args()

    request = JobApplyRequest(
        db_path=args.db,
        limit=args.limit,
        require_login=bool(args.require_login),
        dry_run=bool(args.dry_run),
        fill_only=bool(args.fill_only),
        no_close_tab=bool(args.no_close_tab),
        greetings_dir=args.greetings_dir,
        job_url=args.job_url,
        greeting_file=args.greeting_file,
        greeting_text=args.greeting_text,
        debug=_env_bool("BOSS_DEBUG", False),
    )
    model = JobApplyModel(repository=JobRepository(args.db))
    await model.apply_ready_jobs(request)


if __name__ == "__main__":
    run_async_entrypoint(main())
