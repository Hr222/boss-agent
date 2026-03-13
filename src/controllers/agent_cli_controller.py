"""闭环求职 Agent 的 CLI 控制器。"""

import argparse
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from src.infrastructure.browser.nodriver_runtime import _env_bool, run_async_entrypoint
from src.models.job_agent_flow_model import JobAgentFlowModel, JobAgentFlowRequest
from src.models.job_repository import JobRepository


async def main() -> None:
    """解析命令行参数并运行闭环 Agent。"""
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Run the end-to-end BOSS job agent workflow.")
    parser.add_argument("--db", default="data/boss_jobs.sqlite3")
    parser.add_argument("--strategy", default=os.getenv("BOSS_MATCH_STRATEGY", "backend_ai"))
    parser.add_argument("--target-apply-count", type=int, default=int(os.getenv("BOSS_TARGET_APPLY_COUNT", "15")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BOSS_MIN_MATCH_BATCH_SIZE", "5")))
    parser.add_argument("--threshold", type=float, default=float(os.getenv("BOSS_MATCH_THRESHOLD", "75")))
    parser.add_argument("--greetings-dir", default=os.getenv("BOSS_GREETINGS_DIR", "data/greetings"))
    args = parser.parse_args()

    request = JobAgentFlowRequest(
        db_path=args.db,
        target_apply_count=args.target_apply_count,
        min_match_batch_size=min(max(args.batch_size, 5), 10),
        strategy_id=args.strategy,
        screening_threshold=args.threshold,
        greetings_dir=args.greetings_dir,
        require_login=True,
        debug=_env_bool("BOSS_DEBUG", False),
    )
    model = JobAgentFlowModel(repository=JobRepository(args.db))
    result = await model.run(request)
    print(result)


if __name__ == "__main__":
    run_async_entrypoint(main())
