"""
Build off partner's src/scripts/merge_data.py

This module exposes the merge+clean normalization as a reusable API (not just a script),
so tests and the search engine can call it directly with custom paths.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional


TAG_RE = re.compile(r"<[^>]+>")
PRICE_RE = re.compile(r"-?\d+(?:\.\d+)?")


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = unescape(s)
    s = TAG_RE.sub(" ", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_price(raw: Any) -> Optional[float]:
    if isinstance(raw, (int, float)):
        return float(raw)

    if raw is None:
        return None

    txt = str(raw).strip()
    if not txt:
        return None

    txt = txt.replace(",", "")
    match = PRICE_RE.search(txt)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def _pick(record: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _categories_from_any(value: Any) -> List[str]:
    if isinstance(value, list):
        return flatten_categories(value)
    if isinstance(value, str):
        bits = [x.strip() for x in re.split(r"\s*[>|/;]\s*", value) if x.strip()]
        return bits
    return []


def flatten_categories(categories: Any) -> List[str]:
    if not categories or not isinstance(categories, list):
        return []
    names: List[str] = []
    for c in categories:
        if isinstance(c, dict):
            name = (c.get("name") or "").strip()
            if name:
                names.append(name)
        elif isinstance(c, str) and c.strip():
            names.append(c.strip())

    # Partner dataset often includes leading "Target" category; drop it.
    if names and names[0].lower() == "target":
        names = names[1:]
    return names


def csv_row_to_product(row: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    name = clean_text(
        str(
            _pick(
                row,
                ["name", "title", "product_name", "product_title", "item_name"],
            )
            or ""
        )
    )
    url = str(_pick(row, ["url", "product_url", "link", "product_link", "item_url"]) or "").strip()
    price = parse_price(_pick(row, ["price", "current_price", "sale_price", "final_price", "list_price", "amount"]))
    description = clean_text(str(_pick(row, ["description", "desc", "short_description", "about"]) or ""))

    category_value = _pick(row, ["categories", "category_path", "category", "department"])
    categories = _categories_from_any(category_value)
    category_objs = [{"name": c} for c in categories]

    # Use file-level source (e.g. "amazon", "walmart") so all products from this CSV
    # are labeled consistently, not by row-level seller/store fields.
    pid = _pick(row, ["id", "product_id", "sku", "item_id", "asin", "upc"])
    if pid is None:
        seed = f"{source}|{url or name}"
        pid = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]

    if not name or price is None:
        return None

    return {
        "id": str(pid),
        "name": name,
        "url": url,
        "price": float(price),
        "description": description,
        "categories": category_objs,
        "_source_override": source,
    }


def normalize_products(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    """
    Produces records compatible with partner TF-IDF indexing:
      doc_id, source, id, name, url, price, description, categories, category_path, text
    """
    out: List[Dict[str, Any]] = []
    for p in items:
        pid = p.get("id")
        if pid is None:
            continue

        name = clean_text(p.get("name") or "")
        desc = clean_text(p.get("description") or "")
        price = parse_price(p.get("price"))
        effective_source = str(p.get("_source_override") or source).strip().lower() or source

        if not name:
            continue
        if price is None:
            continue

        cat_path = flatten_categories(p.get("categories"))
        doc_id = f"{effective_source}-{pid}"
        text = " ".join([name, desc, " ".join(cat_path)]).strip()

        out.append(
            {
                "doc_id": doc_id,
                "source": effective_source,
                "id": pid,
                "name": name,
                "url": (p.get("url") or "").strip(),
                "price": float(price),
                "description": desc,
                "categories": p.get("categories", []),
                "category_path": cat_path,
                "text": text,
            }
        )
    return out


def load_json_array(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_live_products(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    """
    Accepts live snapshot products that are either:
    A) already normalized (contains doc_id + text), or
    B) raw-ish records with {id,name,price,description,url,category_path/categories}
    """
    out: List[Dict[str, Any]] = []
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
        if not isinstance(price, (int, float)):
            price = parse_price(price)
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

        out.append(
            {
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
            }
        )
    return out

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
        pass
    # Fallback: extract first number (handles "USD 42", "EUR 10.99", etc.)
    match = PRICE_RE.search(s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            pass
    return None


def parse_json_list(raw: Any) -> List[str]:
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
    try:
        fixed = s.replace('""', '"')
        v = json.loads(fixed)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        return []
    return []


def load_csv_rows(path: Path) -> Iterable[Dict[str, str]]:
    # Amazon CSV has very large JSON-in-CSV fields; raise parser limit.
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(1024 * 1024 * 50)  # 50MB fallback
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # csv.DictReader returns Dict[str, str | None] but we normalize to str keys/values
            yield {k: (v if v is not None else "") for k, v in row.items()}


def normalize_amazon_csv(rows: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
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


def normalize_walmart_csv(rows: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
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


def merge_and_write(
    *,
    bestbuy_path: Path,
    target_path: Path,
    out_path: Path,
    amazon_csv_path: Optional[Path] = None,
    walmart_csv_path: Optional[Path] = None,
    ebay_snapshot_path: Optional[Path] = None,
    additional_sources: Optional[Dict[str, Path]] = None,
) -> List[Dict[str, Any]]:
    bestbuy_raw = load_json_array(bestbuy_path)
    target_raw = load_json_array(target_path)

    merged = normalize_products(bestbuy_raw, "bestbuy") + normalize_products(target_raw, "target")

    if amazon_csv_path and amazon_csv_path.exists():
        merged.extend(normalize_amazon_csv(load_csv_rows(amazon_csv_path)))
    if walmart_csv_path and walmart_csv_path.exists():
        merged.extend(normalize_walmart_csv(load_csv_rows(walmart_csv_path)))

    if ebay_snapshot_path and ebay_snapshot_path.exists():
        ebay_raw = load_json_array(ebay_snapshot_path)
        merged.extend(normalize_live_products(ebay_raw, "ebay"))

    if additional_sources:
        for source_name, csv_path in additional_sources.items():
            if csv_path and csv_path.exists():
                products = [
                    p for p in (
                        csv_row_to_product(r, source_name)
                        for r in load_csv_rows(csv_path)
                    )
                    if p is not None
                ]
                merged.extend(normalize_products(products, source_name))

    # Deduplicate by doc_id
    unique: Dict[str, Dict[str, Any]] = {}
    for p in merged:
        unique[p["doc_id"]] = p
    merged = list(unique.values())
    merged.sort(key=lambda x: (str(x["source"]), str(x["id"])))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
