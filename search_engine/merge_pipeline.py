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

    source_value = str(_pick(row, ["store", "seller_name", "retailer", "merchant", "source"]) or "").strip().lower()
    resolved_source = source_value or source

    pid = _pick(row, ["id", "product_id", "sku", "item_id", "asin", "upc"])
    if pid is None:
        seed = f"{resolved_source}|{url or name}"
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
        "_source_override": resolved_source,
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


def load_csv_rows(path: Path) -> List[Dict[str, Any]]:
    # Allow very large fields (e.g. long product descriptions)
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def merge_and_write(
    *,
    bestbuy_path: Path,
    target_path: Path,
    out_path: Path,
    additional_sources: Optional[Dict[str, Path]] = None,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []

    for source, path in [("bestbuy", bestbuy_path), ("target", target_path)]:
        if path.suffix.lower() == ".csv":
            rows = load_csv_rows(path)
            csv_shaped = [p for p in (csv_row_to_product(r, source) for r in rows) if p is not None]
            merged.extend(normalize_products(csv_shaped, source))
        else:
            merged.extend(normalize_products(load_json_array(path), source))

    for source, path in (additional_sources or {}).items():
        if not path.exists():
            continue
        if path.suffix.lower() == ".csv":
            rows = load_csv_rows(path)
            csv_shaped = [p for p in (csv_row_to_product(r, source) for r in rows) if p is not None]
            merged.extend(normalize_products(csv_shaped, source))
        else:
            merged.extend(normalize_products(load_json_array(path), source))

    # Deduplicate by doc_id
    unique: Dict[str, Dict[str, Any]] = {}
    for p in merged:
        unique[p["doc_id"]] = p
    merged = list(unique.values())
    merged.sort(key=lambda x: (str(x["source"]), str(x["id"])))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
