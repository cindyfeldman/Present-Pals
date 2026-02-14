"""
Build off partner's src/scripts/merge_data.py

This module exposes the merge+clean normalization as a reusable API (not just a script),
so tests and the search engine can call it directly with custom paths.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = unescape(s)
    s = TAG_RE.sub(" ", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


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
        price = p.get("price")

        if not name:
            continue
        if price is None or not isinstance(price, (int, float)):
            continue

        cat_path = flatten_categories(p.get("categories"))
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


def load_json_array(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def merge_and_write(
    *,
    bestbuy_path: Path,
    target_path: Path,
    out_path: Path,
) -> List[Dict[str, Any]]:
    bestbuy_raw = load_json_array(bestbuy_path)
    target_raw = load_json_array(target_path)

    merged = normalize_products(bestbuy_raw, "bestbuy") + normalize_products(target_raw, "target")

    # Deduplicate by doc_id
    unique: Dict[str, Dict[str, Any]] = {}
    for p in merged:
        unique[p["doc_id"]] = p
    merged = list(unique.values())
    merged.sort(key=lambda x: (x["source"], x["id"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged

