"""
Indexed search engine that builds off partner indexing scripts.

Pipeline:
1) Merge+clean raw JSONs into src/data/products_clean.json (partner format)
2) Build/load TF-IDF index in src/index/
3) Query via TF-IDF for fast candidate retrieval
4) Optionally re-rank with the NextGenSearchEngine (persona/occasion ranking)

This lets you demo "we built an index" while still showing next-gen context logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .data_harmonizer import Retailer, UnifiedProduct
from .merge_pipeline import merge_and_write
from .ranking_engine import RankingEngine
from .semantic_filter import OccasionContext, SemanticFilter
from .tfidf_index import IndexPaths, TfidfIndex
from .transient_persona import PersonaBuilder, TransientPersona


@dataclass
class RepoPaths:
    root: Path

    @property
    def src(self) -> Path:
        return self.root / "src"

    @property
    def raw_bestbuy(self) -> Path:
        return self.src / "json" / "complete_product_list.json"

    @property
    def raw_target(self) -> Path:
        return self.src / "json" / "target_data_set.json"

    @property
    def raw_amazon_csv(self) -> Path:
        return self.src / "json" / "amazon-products.csv"

    @property
    def raw_walmart_csv(self) -> Path:
        return self.src / "json" / "walmart-products.csv"

    @property
    def merged_products(self) -> Path:
        return self.src / "data" / "products_clean.json"

    @property
    def ebay_snapshot(self) -> Path:
        return self.src / "json" / "ebay-products.json"

    @property
    def index_dir(self) -> Path:
        return self.src / "index"

    @property
    def personas(self) -> Path:
        return self.src / "config" / "personas.json"


class IndexedGiftSearch:
    def __init__(self, repo_root: str | Path):
        self.paths = RepoPaths(Path(repo_root))
        self.index = TfidfIndex(IndexPaths(self.paths.index_dir))
        self._docs_by_id: Dict[str, Dict[str, Any]] = {}
        self._personas: Dict[str, List[str]] = {}

    def ensure_merged(self) -> None:
        if self.paths.merged_products.exists():
            return
        merge_and_write(
            bestbuy_path=self.paths.raw_bestbuy,
            target_path=self.paths.raw_target,
            out_path=self.paths.merged_products,
            amazon_csv_path=self.paths.raw_amazon_csv,
            walmart_csv_path=self.paths.raw_walmart_csv,
            ebay_snapshot_path=self.paths.ebay_snapshot,
        )

    def ensure_index(
        self,
        *,
        max_docs: Optional[int] = None,
        force_rebuild: bool = False,
        min_docs: int = 0,
    ) -> None:
        self.ensure_merged()
        docs = json.loads(self.paths.merged_products.read_text(encoding="utf-8"))

        should_rebuild = force_rebuild
        if not should_rebuild and self.index.exists():
            # If caller requests a larger sample than what's already indexed, rebuild.
            self.index.load()
            if max_docs is not None and self.index.doc_count < max_docs:
                should_rebuild = True
            if min_docs and self.index.doc_count < min_docs:
                should_rebuild = True
        else:
            should_rebuild = True

        if should_rebuild:
            self.index.build_from_docs(docs, max_docs=max_docs)

        # Load docs map for later enrichment/reranking
        self._docs_by_id = {d["doc_id"]: d for d in docs if d.get("doc_id")}

        if self.paths.personas.exists():
            self._personas = json.loads(self.paths.personas.read_text(encoding="utf-8"))

    def search(
        self,
        *,
        persona: TransientPersona,
        user_query: str,
        recipient_key: str = "",
        k: int = 10,
        candidate_pool: int = 200,
        debug: bool = False,
    ) -> Dict[str, Any]:
        """
        Use TF-IDF for retrieval; then apply next-gen filtering/ranking on candidates.
        """
        self.ensure_index()

        lo, hi = persona.get_price_range()
        persona_terms = self._personas.get((recipient_key or "").strip().lower(), []) if recipient_key else []

        retrieved = self.index.query(
            user_query=user_query,
            persona_terms=persona_terms,
            min_price=lo,
            max_price=None if hi == float("inf") else hi,
            k=max(candidate_pool, k),
        )

        # Convert retrieved docs to UnifiedProduct for downstream logic
        candidates: List[UnifiedProduct] = []
        for r in retrieved:
            d = self._docs_by_id.get(r.doc_id)
            if not d:
                continue

            src = (d.get("source") or "unknown").lower()
            if src == "bestbuy":
                retailer = Retailer.BEST_BUY
            elif src == "target":
                retailer = Retailer.TARGET
            elif src == "amazon":
                retailer = Retailer.AMAZON
            elif src == "walmart":
                retailer = Retailer.WALMART
            else:
                retailer = Retailer.EBAY

            candidates.append(
                UnifiedProduct(
                    id=str(d.get("doc_id")),
                    name=str(d.get("name", "")),
                    price=float(d.get("price", 0.0)),
                    description=str(d.get("description", "")),
                    url=str(d.get("url", "")),
                    retailer=retailer,
                    categories=list(d.get("category_path") or []),
                )
            )

        # Apply semantic filter (occasion/category/tech) on candidate set
        filt = SemanticFilter(persona)
        filtered = filt.apply(candidates, verbose=False)

        # Rank with occasion-aware weights
        weights = OccasionContext.get(persona.occasion or "just_because")
        ranker = RankingEngine(persona, weights)
        ranked = ranker.rank(filtered, limit=k)

        results: List[Dict[str, Any]] = []
        for i, s in enumerate(ranked, 1):
            row = {
                "rank": i,
                "product": {
                    "id": s.product.id,
                    "name": s.product.name,
                    "price": s.product.price,
                    "url": s.product.url,
                    "retailer": s.product.retailer.value,
                    "categories": s.product.categories,
                    "description": s.product.description[:200] + "..." if len(s.product.description) > 200 else s.product.description,
                },
                "score": round(s.total_score, 2),
            }
            if debug:
                row["score_breakdown"] = s.breakdown()
            results.append(row)

        return {
            "success": True,
            "results": results,
            "metadata": {
                "retrieved_candidates": len(candidates),
                "filtered_candidates": len(filtered),
                "returned": len(results),
                "persona": str(persona),
                "recipient_key": recipient_key,
                "user_query": user_query,
                "tfidf_index_present": self.index.exists(),
            },
        }

    def search_from_form(
        self,
        *,
        form_data: Dict[str, Any],
        user_query: str,
        recipient_key: str = "",
        k: int = 10,
        debug: bool = False,
    ) -> Dict[str, Any]:
        persona = PersonaBuilder.build_from_form(form_data)
        return self.search(persona=persona, user_query=user_query, recipient_key=recipient_key, k=k, debug=debug)

