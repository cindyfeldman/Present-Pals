"""
Convenience runner:
- fetch eBay snapshot
- merge local + live datasets
- rebuild index

Usage:
  python src/scripts/fetch_hybrid_live.py --query "gift ideas" --limit 120
"""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def run(cmd: list[str], optional: bool = False) -> None:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        if optional:
            print("  (optional step failed, continuing)")
            return
        raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="", type=str,
                        help="Single eBay query (overrides default multi-query list).")
    parser.add_argument("--limit", default=5000, type=int,
                        help="Total unique eBay items to fetch across all queries.")
    parser.add_argument("--auto-expand-query", action="store_true",
                        help="Expand a single broad --query into multiple long-tail queries.")
    args = parser.parse_args()

    py = sys.executable

    # Optional live fetches (credentials required)
    ebay_cmd = [py, "src/scripts/fetch_ebay.py", "--limit", str(args.limit)]
    if args.query:
        ebay_cmd += ["--query", args.query]
    if args.auto_expand_query:
        ebay_cmd += ["--auto-expand-query"]
    run(ebay_cmd, optional=True)

    # Always rebuild merged corpus/index from whatever is available
    run([py, "src/scripts/merge_data.py"])
    run([py, "src/scripts/build_index.py"])

    print("\nHybrid pipeline complete.")


if __name__ == "__main__":
    main()
