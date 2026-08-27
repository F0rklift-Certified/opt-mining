"""
Standalone entry point for grid generation.

Usage:
    python -m pipeline.grid
    python -m pipeline.grid --verbose
"""

import argparse
import sys
import time

from .generate import run


def main():
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.grid",
        description="Generate the NSW common analysis cell grid (S1-02).",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable detailed logging."
    )
    args = parser.parse_args()

    print("=" * 70)
    print("OPT-MINING GRID GENERATION — S1-02")
    print("=" * 70)

    t0 = time.time()
    result = run(verbose=args.verbose)
    elapsed = time.time() - t0

    print(f"\n{'=' * 70}")
    print("GRID GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Cells: {result['n_cells']:,}")
    print(f"  Grid:  {result['n_cols']} × {result['n_rows']}")
    print(f"  File:  {result['grid_path']}")
    print(f"  Time:  {elapsed:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
