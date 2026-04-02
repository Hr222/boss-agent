"""按新阈值重算已分析岗位入队状态的命令入口。"""

import argparse

from src.models.job_repository import JobRepository


def main() -> None:
    """解析命令行参数并重算入队状态。"""
    parser = argparse.ArgumentParser(description="Recalculate suitability for analyzed jobs by threshold.")
    parser.add_argument("--db", default="data/boss_jobs.sqlite3")
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--limit", type=int, default=0, help="0 means recalculate all analyzed unapplied jobs.")
    args = parser.parse_args()

    repository = JobRepository(args.db)
    result = repository.recalculate_suitability_by_threshold(
        threshold=args.threshold,
        limit=None if args.limit <= 0 else args.limit,
    )
    print(result)


if __name__ == "__main__":
    main()
