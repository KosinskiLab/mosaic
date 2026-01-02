#!python3
"""
Pipeline entrypoint.

Copyright (c) 2025 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import sys
import json
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from mosaic.pipeline.executor import generate_runs, execute_run


def run_wrapper(run_config, skip_complete: bool = False):

    run_id = run_config["run_id"]
    try:
        execute_run(run_config, skip_complete)
        return run_id, None
    except Exception as e:
        return run_id, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Execute Mosaic pipelines from the command line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mosaic-pipeline config.json
  mosaic-pipeline config.json --workers 8
  mosaic-pipeline config.json --index 0
  mosaic-pipeline config.json --index $SLURM_ARRAY_TASK_ID
        """,
    )
    parser.add_argument("config", type=Path, help="Pipeline configuration JSON file")
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1)",
    )
    parser.add_argument(
        "-i",
        "--index",
        type=int,
        default=None,
        help="Run specific index (for job arrays)",
    )
    parser.add_argument(
        "--skip-complete", action="store_true", help="Do not run completed jobs again"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="List runs without executing"
    )

    args = parser.parse_args()

    if not args.config.exists():
        print(f"Error: {args.config} not found", file=sys.stderr)
        return 1

    try:
        with open(args.config, mode="r") as ifile:
            pipeline_config = json.load(ifile)
    except json.JSONDecodeError:
        print("Invalid json file.", file=sys.stderr)
        return 1

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
        futures = {
            pool.submit(run_wrapper, run, args.skip_complete): run for run in runs
        }

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
