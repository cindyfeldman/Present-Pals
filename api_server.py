"""
FastAPI server for the Vite/React frontend.

Frontend expects:
  GET http://localhost:8000/search?recipient=...&min_price=...&max_price=...&q=...
and a JSON response:
  { "gifts": [ { name, price, source, matches, url }, ... ] }

This server builds on the existing indexing pipeline:
- merged data: src/data/products_clean.json
- index artifacts: src/index/*
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from search_engine.merge_pipeline import merge_and_write
from search_engine.tfidf_index import IndexPaths, TfidfIndex


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"

RAW_BESTBUY = SRC_DIR / "json" / "complete_product_list.json"
RAW_TARGET = SRC_DIR / "json" / "target_data_set.json"

MERGED_PATH = SRC_DIR / "data" / "products_clean.json"
INDEX_DIR = SRC_DIR / "index"
PERSONAS_PATH = SRC_DIR / "config" / "personas.json"


app = FastAPI(title="Present Pals API", version="0.1.0")

# Allow local dev frontend (Vite default: http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_index: Optional[TfidfIndex] = None
_meta: Dict[str, Dict[str, Any]] = {}
_personas: Dict[str, List[str]] = {}


def _ensure_data_and_index() -> None:
    global _index, _meta, _personas

    # 1) Merge data if missing
    if not MERGED_PATH.exists():
        merge_and_write(bestbuy_path=RAW_BESTBUY, target_path=RAW_TARGET, out_path=MERGED_PATH)

    # 2) Load/build index
    idx = TfidfIndex(IndexPaths(INDEX_DIR))
    if idx.exists():
        idx.load()
    else:
        docs = json.loads(MERGED_PATH.read_text(encoding="utf-8"))
        idx.build_from_docs(docs)

    _index = idx
    _meta = idx.meta

    # 3) Load personas for expansion
    if PERSONAS_PATH.exists():
        _personas = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    else:
        _personas = {}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/search")
def search(
    recipient: str = Query(default="", description="persona key (mom/dad/friend/...)"),
    min_price: Optional[float] = Query(default=None),
    max_price: Optional[float] = Query(default=None),
    q: str = Query(default="", description="free text query"),
    k: int = Query(default=10, ge=1, le=50),
) -> Dict[str, Any]:
    """
    TF‑IDF search with persona expansion.
    Returns `gifts` in the exact shape the current React UI expects.
    """
    if _index is None:
        _ensure_data_and_index()

    assert _index is not None

    recipient_key = (recipient or "").strip().lower()
    persona_terms = _personas.get(recipient_key, []) if recipient_key else []

    results = _index.query(
        user_query=q,
        persona_terms=persona_terms,
        min_price=min_price,
        max_price=max_price,
        k=k,
    )

    gifts: List[Dict[str, Any]] = []
    for r in results:
        m = _meta.get(r.doc_id, {})
        gifts.append(
            {
                "name": m.get("name", ""),
                "price": float(m.get("price", 0.0) or 0.0),
                "source": (m.get("source", "") or "").lower(),
                "matches": r.matched_terms,
                "url": m.get("url", ""),
            }
        )

    return {"gifts": gifts}

