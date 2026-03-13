"""CLI controller for Boss job search collection."""

import argparse
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from src.infrastructure.browser.nodriver_runtime import _env_bool, run_async_entrypoint
from src.models.resume_store import ResumeStore
from src.models.job_repository import JobRepository
from src.models.job_search_model import JobSearchModel, JobSearchRequest


async def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Open BOSS job search page using nodriver.")
    parser.add_argument("--keyword", default=os.getenv("BOSS_KEYWORD", "Python开发"))
    parser.add_argument("--city", default=os.getenv("BOSS_CITY", "深圳"))
    parser.add_argument("--city-code", default=os.getenv("BOSS_CITY_CODE", ""))
    parser.add_argument("--limit", type=int, default=int(os.getenv("BOSS_JOB_LIMIT", "20")))
    parser.add_argument("--db", default="data/boss_jobs.sqlite3")
    parser.add_argument("--require-login", action="store_true", help="Wait for manual login before collecting links.")
    parser.add_argument("--no-collect", action="store_true", help="Only open the page; do not collect job links.")
    args = parser.parse_args()
    resume = ResumeStore().load_resume()
    exclude_company_names: tuple[str, ...] = ()
    if resume:
        explicit_names = [item.strip() for item in getattr(resume, "excluded_company_names", []) if (item or "").strip()]
        if explicit_names:
            exclude_company_names = tuple(dict.fromkeys(explicit_names))
        else:
            exclude_company_names = tuple(
                dict.fromkeys(
                    work.company.strip()
                    for work in resume.work_experience
                    if (work.company or "").strip()
                )
            )

    request = JobSearchRequest(
        db_path=args.db,
        keyword=args.keyword,
        city=args.city,
        city_code=args.city_code,
        limit=args.limit,
        require_login=bool(args.require_login),
        no_collect=bool(args.no_collect),
        debug=_env_bool("BOSS_DEBUG", False),
        exclude_company_names=exclude_company_names,
    )
    model = JobSearchModel(repository=JobRepository(args.db))
    await model.search_jobs(request)


if __name__ == "__main__":
    run_async_entrypoint(main())
