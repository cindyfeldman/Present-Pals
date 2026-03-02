import json
import re
import csv
import sys
from html import unescape
from pathlib import Path
from typing import Any, Optional

SRC_DIR = Path(__file__).resolve().parent.parent  
RAW_DIR = SRC_DIR / "json"
OUT_DIR = SRC_DIR / "data" 
LIVE_DIR = OUT_DIR / "live"

BESTBUY_PATH = RAW_DIR / "complete_product_list.json"
TARGET_PATH = RAW_DIR / "target_data_set.json"
AMAZON_CSV_PATH = RAW_DIR / "amazon-products.csv"
WALMART_CSV_PATH = RAW_DIR / "walmart-products.csv"
# eBay snapshot lives next to the other source data so teammates can commit it
EBAY_JSON_PATH = RAW_DIR / "ebay-products.json"
OUT_PATH = OUT_DIR / "products_clean.json"

TAG_RE = re.compile(r"<[^>]+>")  

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = unescape(s)
    s = TAG_RE.sub(" ", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def flatten_categories(categories) -> list[str]:
    if not categories:
        return []
    names = []
    for c in categories:
        name = (c.get("name") or "").strip()
        if name:
            names.append(name)
    if names and names[0].lower() == "target":
        names = names[1:]
    return names

def normalize_products(items: list[dict], source: str) -> list[dict]:
    out = []
    for p in items:
        pid = p.get("id")
        if pid is None:
            continue

        name = clean_text(p.get("name") or "")
        desc = clean_text(p.get("description") or "")
        price = p.get("price")

        if not name:
            continue
        if price is None or not isinstance(price, (int, float)):
            continue

        cat_path = flatten_categories(p.get("categories"))

        doc_id = f"{source}-{pid}"
        text = " ".join([name, desc, " ".join(cat_path)]).strip()

        out.append({
            "doc_id": doc_id,
            "source": source,
            "id": pid,
            "name": name,
            "url": (p.get("url") or "").strip(),
            "price": float(price),
            "description": desc,
            "categories": p.get("categories", []),   
            "category_path": cat_path,              
            "text": text,                           
        })
    return out

def load_json_array(path: Path) -> list[dict]:
    """Load a JSON array from disk."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _strip_outer_quotes(s: str) -> str:
    s = (s or "").strip()
    while len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].strip()
    return s


def parse_price(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except Exception:
            return None
    s = _strip_outer_quotes(str(raw))
    if not s or s.lower() == "null":
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def parse_json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = (raw if isinstance(raw, str) else str(raw)).strip()
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    # Common CSV-escaped JSON: [""A"",""B""]
    try:
        fixed = s.replace('""', '"')
        v = json.loads(fixed)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        return []
    return []


def load_csv_rows(path: Path):
    # Amazon CSV has very large JSON-in-CSV fields; raise parser limit.
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(1024 * 1024 * 50)  # 50MB fallback
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def normalize_amazon_csv(rows) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        asin = (r.get("asin") or r.get("input_asin") or r.get("parent_asin") or "").strip()
        title = clean_text(r.get("title") or "")
        if not asin or not title:
            continue

        price = parse_price(r.get("final_price"))
        if price is None:
            continue

        desc = clean_text(r.get("description") or "")
        url = (r.get("url") or r.get("origin_url") or "").strip()
        cat_path = parse_json_list(r.get("categories"))

        doc_id = f"amazon-{asin}"
        text = " ".join([title, desc, " ".join(cat_path)]).strip()

        out.append(
            {
                "doc_id": doc_id,
                "source": "amazon",
                "id": asin,
                "name": title,
                "url": url,
                "price": float(price),
                "description": desc,
                "categories": [{"name": c} for c in cat_path],
                "category_path": cat_path,
                "text": text,
            }
        )
    return out


def normalize_walmart_csv(rows) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        pid = (r.get("product_id") or r.get("sku") or "").strip()
        name = clean_text(r.get("product_name") or "")
        if not pid or not name:
            continue

        price = parse_price(r.get("final_price"))
        if price is None:
            continue

        desc = clean_text(r.get("description") or "")
        url = (r.get("url") or "").strip()
        cat_path = parse_json_list(r.get("categories"))

        doc_id = f"walmart-{pid}"
        text = " ".join([name, desc, " ".join(cat_path)]).strip()

        out.append(
            {
                "doc_id": doc_id,
                "source": "walmart",
                "id": pid,
                "name": name,
                "url": url,
                "price": float(price),
                "description": desc,
                "categories": [{"name": c} for c in cat_path],
                "category_path": cat_path,
                "text": text,
            }
        )
    return out


def normalize_live_products(items: list[dict], source: str) -> list[dict]:
    """
    Accepts live products that are either:
    A) already normalized (contains doc_id + text), or
    B) raw-ish records with {id,name,price,description,url,category_path/categories}
    """
    out = []
    for p in items:
        # Already normalized shape
        if p.get("doc_id") and p.get("text"):
            out.append(p)
            continue

        pid = p.get("id")
        if pid is None:
            continue

        name = clean_text(p.get("name") or "")
        desc = clean_text(p.get("description") or "")
        price = p.get("price")
        if not name:
            continue
        if price is None or not isinstance(price, (int, float)):
            continue

        # category_path preferred; fallback to flatten categories
        cat_path = p.get("category_path") or flatten_categories(p.get("categories"))
        if not isinstance(cat_path, list):
            cat_path = []
        cat_path = [str(c).strip() for c in cat_path if str(c).strip()]

        doc_id = f"{source}-{pid}"
        text = " ".join([name, desc, " ".join(cat_path)]).strip()

        out.append({
            "doc_id": doc_id,
            "source": source,
            "id": pid,
            "name": name,
            "url": (p.get("url") or "").strip(),
            "price": float(price),
            "description": desc,
            "categories": p.get("categories", []),
            "category_path": cat_path,
            "text": text,
        })
    return out

def main():
    if not BESTBUY_PATH.exists():
        raise FileNotFoundError(f"Missing: {BESTBUY_PATH}")
    if not TARGET_PATH.exists():
        raise FileNotFoundError(f"Missing: {TARGET_PATH}")

    bestbuy_raw = load_json_array(BESTBUY_PATH)
    target_raw = load_json_array(TARGET_PATH)

    bestbuy_norm = normalize_products(bestbuy_raw, "bestbuy")
    target_norm = normalize_products(target_raw, "target")

    merged = bestbuy_norm + target_norm

    # Optional CSV sources (checked-in snapshots)
    if AMAZON_CSV_PATH.exists():
        amazon_norm = normalize_amazon_csv(load_csv_rows(AMAZON_CSV_PATH))
        merged.extend(amazon_norm)
        print(f"Loaded Amazon CSV records: {len(amazon_norm)}")
    if WALMART_CSV_PATH.exists():
        walmart_norm = normalize_walmart_csv(load_csv_rows(WALMART_CSV_PATH))
        merged.extend(walmart_norm)
        print(f"Loaded Walmart CSV records: {len(walmart_norm)}")

    # Optional eBay snapshot (committed alongside other source data)
    if EBAY_JSON_PATH.exists():
        ebay_raw = load_json_array(EBAY_JSON_PATH)
        ebay_norm = normalize_live_products(ebay_raw, "ebay")
        merged.extend(ebay_norm)
        print(f"Loaded eBay records: {len(ebay_norm)}")

    unique = {}
    for p in merged:
        unique[p["doc_id"]] = p
    merged = list(unique.values())

    merged.sort(key=lambda x: (x["source"], x["id"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    if merged:
        print("\nSample record:\n", json.dumps(merged[0], indent=2))

if __name__ == "__main__":
    main()