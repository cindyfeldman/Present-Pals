import json
import re
from html import unescape
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent  
RAW_DIR = SRC_DIR / "data" / "raw"
OUT_DIR = SRC_DIR / "data" / "processed"

BESTBUY_PATH = RAW_DIR / "complete_product_list.json"
TARGET_PATH = RAW_DIR / "target_data_set.json"
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