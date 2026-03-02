"""
Demo: use partner-style TF-IDF index + next-gen persona/occasion reranking.

Run:
  python indexed_demo.py --q "knife" --recipient mom
"""

import argparse
from pathlib import Path

from search_engine.indexed_engine import IndexedGiftSearch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", default="knife", type=str)
    parser.add_argument("--recipient", default="", type=str, help="mom/dad/sister/brother/for him/for her/friend")
    parser.add_argument("--occasion", default="Wedding", type=str)
    parser.add_argument("--budget", default="medium", type=str)
    parser.add_argument("--tech", default="medium", type=str)
    parser.add_argument("--k", default=10, type=int)
    parser.add_argument("--rebuild_index", action="store_true", help="Force rebuild TF-IDF index")
    args = parser.parse_args()

    engine = IndexedGiftSearch(repo_root=Path(__file__).resolve().parent)
    # If an older small index exists, rebuild it for better demo results.
    engine.ensure_index(force_rebuild=bool(args.rebuild_index), min_docs=3000)
    results = engine.search_from_form(
        form_data={
            "interests": ["Cooking"] if "knife" in args.q.lower() else ["Technology"],
            "tech_level": args.tech,
            "budget": args.budget,
            "occasion": args.occasion,
        },
        user_query=args.q,
        recipient_key=args.recipient,
        k=args.k,
        debug=True,
    )

    print("\n--- INDEXED SEARCH ---")
    print(results["metadata"])
    for row in results["results"][:5]:
        p = row["product"]
        print(f"\n{row['rank']}. {p['name']}")
        print(f"   ${p['price']:.2f} | {p['retailer']}")
        print(f"   score={row['score']:.2f}")
        b = row.get("score_breakdown")
        if b:
            print(f"   breakdown: {b}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

