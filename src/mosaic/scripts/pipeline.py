import sys
import json
import argparse

from pathlib import Path
from mosaic.pipeline.executor import generate_runs, execute_run
from concurrent.futures import ProcessPoolExecutor, as_completed


def execute_run_wrapper(run_config):

    run_id = run_config["run_id"]
    try:
        execute_run(run_config)
        return run_id, None
    except Exception as e:
        return run_id, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Execute Mosaic pipelines from command line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mosaic_pipeline config.json
  mosaic_pipeline config.json --workers 8
  mosaic_pipeline config.json --index 0
  mosaic_pipeline config.json --index $SLURM_ARRAY_TASK_ID
        """,
    )
    parser.add_argument("config", type=Path, help="Pipeline configuration JSON file")
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1)",
    )
    parser.add_argument(
        "--index",
        "-i",
        type=int,
        default=None,
        help="Run specific index (for job arrays)",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="List runs without executing"
    )

    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: {args.config} not found", file=sys.stderr)
        return 1

    with open(args.config, mode="r") as ifile:
        pipeline_config = json.load(ifile)

    try:
        runs = generate_runs(pipeline_config)
    except Exception as e:
        print(f"Error generating runs: {e}", file=sys.stderr)
        return 1

    if not runs:
        print("No runs to execute", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Total runs: {len(runs)}")
        for i, run in enumerate(runs):
            print(f"  [{i}] {run['run_id']}")
        return 0

    if args.index is not None:
        if args.index < 0 or args.index >= len(runs):
            print(
                f"Error: index {args.index} out of range [0, {len(runs)-1}]",
                file=sys.stderr,
            )
            return 1
        runs = [runs[args.index]]
        print(f"Executing run {args.index}: {runs[0]['run_id']}")

    total = len(runs)

    completed = 0
    with ProcessPoolExecutor(max_workers=args.workers, max_tasks_per_child=1) as pool:
        futures = {pool.submit(execute_run_wrapper, run): run for run in runs}

        for future in as_completed(futures):
            run = futures[future]
            completed += 1
            try:
                run_id, error = future.result()
                if error:
                    print(
                        f"[{completed}/{total}] {run_id}: Error - {error}",
                        file=sys.stderr,
                    )
                else:
                    print(f"[{completed}/{total}] {run_id}: Done")
            except Exception as e:
                print(
                    f"[{completed}/{total}] {run['run_id']}: "
                    f"Unexpected error - {e}",
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
