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
from datetime import date, timedelta
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
RAW_AMAZON_CSV = SRC_DIR / "json" / "amazon-products.csv"
RAW_WALMART_CSV = SRC_DIR / "json" / "walmart-products.csv"

MERGED_PATH = SRC_DIR / "data" / "products_clean.json"
INDEX_DIR = SRC_DIR / "index"
PERSONAS_PATH = SRC_DIR / "config" / "personas.json"
EBAY_SNAPSHOT_PATH = SRC_DIR / "json" / "ebay-products.json"


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
        merge_and_write(
            bestbuy_path=RAW_BESTBUY,
            target_path=RAW_TARGET,
            out_path=MERGED_PATH,
            amazon_csv_path=RAW_AMAZON_CSV,
            walmart_csv_path=RAW_WALMART_CSV,
            ebay_snapshot_path=EBAY_SNAPSHOT_PATH,
        )

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


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    weekday: Monday=0 .. Sunday=6
    n: 1..5
    """
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(days=7 * (n - 1))
    return d


def _implicit_context_terms(today: date) -> tuple[str, List[str]]:
    """
    Implicit context: infer seasonal/holiday intent from current date.
    Returns (context_name, expansion_terms) for low-weight retrieval expansion.
    """
    def within(days: int, target: date) -> bool:
        return abs((today - target).days) <= days

    valentines = date(today.year, 2, 14)
    mothers_day = _nth_weekday_of_month(today.year, 5, 6, 2)  # 2nd Sunday in May
    fathers_day = _nth_weekday_of_month(today.year, 6, 6, 3)  # 3rd Sunday in June
    halloween = date(today.year, 10, 31)
    christmas = date(today.year, 12, 25)

    if within(7, valentines):
        return ("valentines", ["jewelry", "flowers", "chocolate", "perfume", "romantic", "heart"])
    if within(10, mothers_day):
        return ("mothers_day", ["beauty", "spa", "home decor", "kitchen", "coffee", "jewelry"])
    if within(10, fathers_day):
        return ("fathers_day", ["tools", "audio", "grill", "outdoor", "fitness", "watch"])
    if within(14, halloween):
        return ("halloween", ["costume", "party", "novelty", "decor", "candy"])
    if within(21, christmas):
        return ("christmas", ["toys", "games", "electronics", "gift", "holiday"])
    if today.month in (8, 9):
        return ("back_to_school", ["laptop", "tablet", "backpack", "notebook", "planner", "office"])
    return ("none", [])


def _implicit_rerank_boost(context_name: str, name: str, matches: List[str]) -> float:
    """
    Small boost to top-k ranking based on implicit context.
    TF-IDF cosine is around 0..1, so boost should stay small.
    """
    if context_name == "none":
        return 0.0

    n = (name or "").lower()
    mset = set(matches or [])
    boost = 0.0

    if context_name == "valentines":
        if any(k in n for k in ["jewelry", "heart", "rose", "perfume", "chocolate"]):
            boost += 0.08
    elif context_name == "mothers_day":
        if any(k in n for k in ["beauty", "spa", "kitchen", "coffee", "jewelry", "decor"]):
            boost += 0.06
    elif context_name == "fathers_day":
        if any(k in n for k in ["tools", "audio", "grill", "outdoor", "watch", "fitness"]):
            boost += 0.06
    elif context_name == "halloween":
        if any(k in n for k in ["costume", "party", "novelty", "decor", "candy"]):
            boost += 0.05
    elif context_name == "christmas":
        if any(k in n for k in ["toy", "game", "gift", "holiday", "electronics"]):
            boost += 0.05
    elif context_name == "back_to_school":
        if any(k in n for k in ["laptop", "tablet", "backpack", "notebook", "office", "planner"]):
            boost += 0.05

    # tiny bonus if retrieval already matched expansion terms
    if mset:
        boost += min(0.03, 0.005 * len(mset))
    return min(boost, 0.12)


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
    implicit_context, implicit_terms = _implicit_context_terms(date.today())
    expansion_terms = persona_terms + implicit_terms

    results = _index.query(
        user_query=q,
        persona_terms=expansion_terms,
        min_price=min_price,
        max_price=max_price,
        k=max(k, 50),  # retrieve a slightly larger pool before implicit rerank
    )

    scored: List[tuple[float, Dict[str, Any]]] = []
    for r in results:
        m = _meta.get(r.doc_id, {})
        gift = {
            "name": m.get("name", ""),
            "price": float(m.get("price", 0.0) or 0.0),
            "source": (m.get("source", "") or "").lower(),
            "matches": r.matched_terms,
            "url": m.get("url", ""),
        }
        final_score = float(r.cosine) + _implicit_rerank_boost(implicit_context, gift["name"], r.matched_terms)
        scored.append((final_score, gift))

    scored.sort(key=lambda x: x[0], reverse=True)
    gifts = [g for _, g in scored[:k]]

    return {
        "gifts": gifts,
        "meta": {
            "implicit_context": implicit_context,
            "implicit_terms_used": implicit_terms,
        },
    }

