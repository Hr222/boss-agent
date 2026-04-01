"""批量岗位匹配命令入口。"""

import argparse
import os

from src.config.settings import Config
from src.models.job_repository import JobRepository
from src.models.job_screening_model import JobScreeningModel


def main() -> None:
    """解析命令行参数并运行批量匹配。"""
    parser = argparse.ArgumentParser(description="Analyze pending jobs in SQLite and label suitability + greeting.")
    parser.add_argument("--db", default="data/boss_jobs.sqlite3")
    parser.add_argument("--strategy", default=os.getenv("BOSS_MATCH_STRATEGY", "backend_ai"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("BOSS_MATCH_LIMIT", "10")))
    parser.add_argument("--threshold", type=float, default=float(os.getenv("BOSS_MATCH_THRESHOLD", "75")))
    parser.add_argument("--llm-provider", default=os.getenv("LLM_PROVIDER", Config.get_llm_provider()))
    args = parser.parse_args()

    api_key = Config.get_llm_api_key(args.llm_provider)
    if not api_key or api_key == "your_api_key_here":
        raise SystemExit(f"Missing API key for provider={args.llm_provider}; cannot call LLM.")

    model = JobScreeningModel(repository=JobRepository(args.db))
    model.use_strategy(args.strategy)
    model.use_llm_provider(args.llm_provider)
    results = model.analyze_pending_jobs(limit=args.limit, threshold=args.threshold)

    if not results:
        print("No pending jobs (is_suitable is NULL and jd is not empty).")
        return

    for item in results:
        if item.status != "ok":
            print(f"失败 {item.job_title or item.job_url} | analyze failed")
            continue
        print(
            f"成功 {item.job_title} | score={item.match_score:.1f}({item.match_level}) | "
            f"recommended={item.is_recommended} | suitable={item.is_suitable} | "
            "greeting=已写入数据库，发送成功后再落归档文件"
        )


if __name__ == "__main__":
    main()
