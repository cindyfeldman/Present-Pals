import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

import requests


SRC_DIR = Path(__file__).resolve().parent.parent
# Save alongside the other committed source data files (amazon-products.csv, walmart-products.csv)
OUT_PATH = SRC_DIR / "json" / "ebay-products.json"

# eBay production endpoints (Buy Browse API)
EBAY_IDENTITY_BASE = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_BASE = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# eBay hard-caps each request at 200 items.
PAGE_SIZE = 200
# In practice the Browse API free tier rejects requests once offset reaches
# ~1000-1200 for a given query (HTTP 400).  Keep to 5 pages (1000 items) per
# query to stay safe.
MAX_PAGES_PER_QUERY = 5
# Absolute ceiling across all queries per run.
GLOBAL_ITEM_LIMIT = 10_000
# Seconds to wait between paginated requests (be a polite API citizen).
PAGE_DELAY = 1.0

# Default gift-focused queries used when --queries is not specified.
# Multiple targeted queries give a more diverse product set than one broad query.
DEFAULT_QUERIES = [
    "gift ideas",
    "gift for her",
    "gift for him",
    "birthday gift",
    "holiday gift",
    "kitchen gift",
    "tech gadget gift",
    "outdoor gift",
    "beauty gift",
    "home decor gift",
]

# If the user gives one broad query but asks for many items, expand into
# related long-tail queries so we can collect more unique results politely.
QUERY_EXPANSION_SUFFIXES = [
    "for women",
    "for men",
    "for kids",
    "for teens",
    "under 25",
    "under 50",
    "under 100",
    "handmade",
    "personalized",
    "unique",
    "funny",
    "practical",
    "premium",
    "tech",
    "kitchen",
    "home",
    "outdoor",
    "fitness",
    "beauty",
    "office",
    "travel",
    "pet lover",
    "birthday",
    "anniversary",
    "christmas",
]


def get_env(name: str, required: bool = True) -> str:
    import os

    val = os.getenv(name, "").strip()
    if required and not val:
        raise RuntimeError(f"Missing environment variable: {name}")
    return val


def get_access_token(client_id: str, client_secret: str) -> str:
    auth = (client_id, client_secret)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    resp = requests.post(EBAY_IDENTITY_BASE, headers=headers, data=data, auth=auth, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def parse_price(raw: Dict[str, Any]) -> float:
    try:
        return float(raw.get("value", 0.0))
    except Exception:
        return 0.0


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item_id = item.get("itemId") or item.get("legacyItemId") or item.get("epid")
    title = (item.get("title") or "").strip()
    if not item_id or not title:
        return {}

    categories = item.get("categories") or []
    category_path = [c.get("categoryName", "").strip() for c in categories if isinstance(c, dict)]
    category_path = [c for c in category_path if c]

    desc = (item.get("shortDescription") or item.get("subtitle") or "").strip()
    url = (item.get("itemWebUrl") or "").strip()
    price = parse_price((item.get("price") or {}))
    if price <= 0:
        # Skip unknown or zero-price records for now
        return {}

    doc_id = f"ebay-{item_id}"
    text = " ".join([title, desc, " ".join(category_path)]).strip()

    return {
        "doc_id": doc_id,
        "source": "ebay",
        "id": item_id,
        "name": title,
        "url": url,
        "price": price,
        "description": desc,
        "categories": [],
        "category_path": category_path,
        "text": text,
    }


def fetch_page(
    token: str, query: str, page_size: int, offset: int
) -> tuple[List[Dict[str, Any]], int] | None:
    """
    Fetch one page of results.
    Returns (normalized_items, total_available), or None if the API signals
    we've gone past the accessible range (HTTP 400/404).
    """
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": query,
        "limit": str(max(page_size, 1)),
        "offset": str(offset),
    }
    resp = requests.get(EBAY_BROWSE_BASE, headers=headers, params=params, timeout=30)

    # 400/404 at deep offsets means we've hit the API's per-query result cap.
    if resp.status_code in (400, 404):
        print(f"    [{query}] offset={offset}: API returned {resp.status_code} "
              f"— result cap reached, stopping this query.")
        return None

    resp.raise_for_status()
    data = resp.json()
    raw_items = data.get("itemSummaries", []) or []
    total = int(data.get("total", 0))

    normalized: List[Dict[str, Any]] = []
    for it in raw_items:
        n = normalize_item(it)
        if n:
            normalized.append(n)
    return normalized, total


def fetch_query(
    token: str,
    query: str,
    per_query_limit: int,
    seen_ids: set,
    max_pages_per_query: int,
) -> List[Dict[str, Any]]:
    """
    Paginate through one query, skipping items already seen (dedup across queries).
    Returns newly-fetched items for this query.
    """
    per_query_limit = max(1, min(per_query_limit, PAGE_SIZE * max_pages_per_query))
    out: List[Dict[str, Any]] = []
    offset = 0

    while len(out) < per_query_limit:
        # Always request a full PAGE_SIZE; trimming causes 400s on some tiers.
        result = fetch_page(token, query, PAGE_SIZE, offset)
        if result is None:
            # Hit the API's accessible-result cap for this query — stop cleanly.
            break

        page_items, total_available = result
        new_this_page = 0
        for item in page_items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                out.append(item)
                new_this_page += 1

        offset += PAGE_SIZE
        pages_done = offset // PAGE_SIZE
        print(f"    [{query}] page {pages_done}: +{new_this_page} new "
              f"(query total: {len(out)}, API total available: {total_available})")

        if offset >= total_available or pages_done >= max_pages_per_query or len(page_items) == 0:
            break

        if len(out) < per_query_limit:
            time.sleep(PAGE_DELAY)

    return out


def fetch_items_multi_query(
    token: str,
    queries: List[str],
    total_limit: int,
    max_pages_per_query: int,
) -> List[Dict[str, Any]]:
    """
    Fetch up to `total_limit` unique items across all `queries`.
    Items are deduplicated by eBay item ID across queries.
    Each query contributes at most total_limit // len(queries) items,
    with remainder distributed to earlier queries.
    """
    total_limit = max(1, min(total_limit, GLOBAL_ITEM_LIMIT))
    per_query_cap = PAGE_SIZE * max_pages_per_query
    q_count = max(len(queries), 1)
    per_query_base = total_limit // q_count
    per_query_remainder = total_limit % q_count

    all_items: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for i, query in enumerate(queries, 1):
        remaining = total_limit - len(all_items)
        if remaining <= 0:
            break
        fair_share = per_query_base + (1 if i <= per_query_remainder else 0)
        limit_this_query = min(max(1, fair_share), remaining, per_query_cap)
        print(f"\nQuery {i}/{len(queries)}: '{query}' (want up to {limit_this_query} items)")
        new_items = fetch_query(
            token=token,
            query=query,
            per_query_limit=limit_this_query,
            seen_ids=seen_ids,
            max_pages_per_query=max_pages_per_query,
        )
        all_items.extend(new_items)
        print(f"  -> Got {len(new_items)} new items. Running total: {len(all_items)}")

        # Small extra pause between different queries
        if i < len(queries) and len(all_items) < total_limit:
            time.sleep(PAGE_DELAY)

    return all_items


def build_queries(user_query: str, user_queries: List[str] | None, total_limit: int, auto_expand: bool) -> List[str]:
    if user_queries:
        return [q.strip() for q in user_queries if q.strip()]

    if user_query:
        base = user_query.strip()
        if not auto_expand:
            return [base]

        # Estimate how many query buckets we need under per-query caps.
        needed_queries = max(1, math.ceil(total_limit / (PAGE_SIZE * MAX_PAGES_PER_QUERY)))
        needed_queries = min(needed_queries, 1 + len(QUERY_EXPANSION_SUFFIXES))
        queries = [base]
        if needed_queries > 1:
            for suffix in QUERY_EXPANSION_SUFFIXES:
                queries.append(f"{base} {suffix}")
                if len(queries) >= needed_queries:
                    break
        return queries

    return DEFAULT_QUERIES


def main() -> None:
    global PAGE_DELAY
    parser = argparse.ArgumentParser(
        description="Fetch eBay products via paginated multi-query and save normalized snapshot."
    )
    parser.add_argument(
        "--query",
        default="",
        type=str,
        help="Single query string. Ignored if --queries is set. "
             "Defaults to a built-in list of gift-focused queries.",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=None,
        help="One or more search queries. Overrides --query and the default list.",
    )
    parser.add_argument(
        "--limit",
        default=1000,
        type=int,
        help=(
            f"Total unique items to collect across all queries (max {GLOBAL_ITEM_LIMIT}). "
            f"Each query is capped at {PAGE_SIZE * MAX_PAGES_PER_QUERY} items by the API."
        ),
    )
    parser.add_argument(
        "--auto-expand-query",
        action="store_true",
        help=(
            "If using --query and requesting many items, automatically fan out to "
            "related long-tail queries to increase unique coverage."
        ),
    )
    parser.add_argument(
        "--max-pages-per-query",
        default=MAX_PAGES_PER_QUERY,
        type=int,
        help=(
            "Max pages per query (200 items/page). Keep low to avoid deep-offset "
            "caps; default is a safe value."
        ),
    )
    parser.add_argument(
        "--page-delay",
        default=PAGE_DELAY,
        type=float,
        help="Seconds to wait between page/query requests.",
    )
    parser.add_argument("--out", default=str(OUT_PATH), type=str)
    args = parser.parse_args()

    PAGE_DELAY = max(0.0, args.page_delay)
    max_pages_per_query = max(1, args.max_pages_per_query)
    queries = build_queries(
        user_query=args.query,
        user_queries=args.queries,
        total_limit=args.limit,
        auto_expand=bool(args.auto_expand_query),
    )
    per_query_cap = PAGE_SIZE * max_pages_per_query
    theoretical_max = min(GLOBAL_ITEM_LIMIT, len(queries) * per_query_cap)
    if args.limit > theoretical_max:
        print(
            f"Requested {args.limit} items, but with {len(queries)} queries and "
            f"max_pages_per_query={max_pages_per_query}, the theoretical ceiling is "
            f"{theoretical_max}. Consider adding more --queries or increasing "
            f"--max-pages-per-query (if your key tier allows deeper offsets)."
        )

    client_id = get_env("EBAY_CLIENT_ID")
    client_secret = get_env("EBAY_CLIENT_SECRET")
    token = get_access_token(client_id, client_secret)

    print(
        f"Fetching up to {args.limit} eBay items across {len(queries)} queries "
        f"(per-query cap: {per_query_cap}, page delay: {PAGE_DELAY:.2f}s)"
    )
    try:
        items = fetch_items_multi_query(
            token=token,
            queries=queries,
            total_limit=args.limit,
            max_pages_per_query=max_pages_per_query,
        )
    except Exception as exc:
        print(f"\nFetch interrupted: {exc}")
        items = []

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # If the run produced 0 items but an older snapshot exists, keep the old one.
    if not items and out_path.exists():
        print(f"\nNo new items fetched; keeping existing snapshot at {out_path}")
    else:
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved {len(items)} eBay records -> {out_path}")


if __name__ == "__main__":
    main()
