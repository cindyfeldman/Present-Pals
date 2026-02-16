"""
Multi-factor reranking using only fields available in products_clean.json:
name, description, category_path, price, source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import math

from .data_harmonizer import UnifiedProduct
from .semantic_filter import OccasionWeights
from .transient_persona import TransientPersona


@dataclass
class ProductScore:
    product: UnifiedProduct
    total_score: float
    price: float
    match: float
    tech: float
    uniqueness: float
    quality: float

    def breakdown(self) -> Dict[str, float]:
        return {
            "total": round(self.total_score, 2),
            "price": round(self.price, 2),
            "match": round(self.match, 2),
            "tech": round(self.tech, 2),
            "uniqueness": round(self.uniqueness, 2),
            "quality": round(self.quality, 2),
        }


class RankingEngine:
    def __init__(self, persona: TransientPersona, weights: OccasionWeights):
        self.persona = persona
        self.weights = weights

    def _price_score(self, p: UnifiedProduct) -> float:
        lo, hi = self.persona.get_price_range()
        span = (hi - lo) if hi != float("inf") else 1000.0
        span = max(span, 1e-9)
        normalized = 1.0 - ((p.price - lo) / span)
        return max(0.0, min(10.0, normalized * 10.0 * self.weights.price_weight))

    def _match_score(self, p: UnifiedProduct) -> float:
        # Simple overlap: how many interest-derived keywords appear in text
        prefs = [c.lower() for c in self.persona.get_category_preferences()]
        blob = f"{p.name} {p.description} {' '.join(p.categories)}".lower()
        if not prefs:
            return 5.0
        hits = sum(1 for pref in prefs if pref.lower() in blob)
        return min(10.0, (hits / max(1, len(prefs))) * 10.0)

    def _tech_score(self, p: UnifiedProduct) -> float:
        kw = self.persona.tech_keywords()
        exclude = kw.get("exclude", [])
        prefer = kw.get("prefer", [])
        blob = f"{p.name} {p.description}".lower()
        penalty = sum(2.0 for w in exclude if w in blob)
        bonus = sum(1.5 for w in prefer if w in blob)
        return max(0.0, min(10.0, 5.0 + bonus - penalty))

    def _uniqueness_score(self, p: UnifiedProduct, category_counts: Dict[str, int]) -> float:
        unique_kw = ["unique", "custom", "personalized", "limited", "collector", "vintage", "handmade", "novelty", "quirky", "weird", "funny", "gag"]
        blob = f"{p.name} {p.description}".lower()
        kw_hits = sum(1 for w in unique_kw if w in blob)
        rarity = 0.0
        for c in p.categories:
            rarity += 1.0 / math.log(category_counts.get(c, 1) + 1)
        rarity = (rarity / len(p.categories)) if p.categories else 0.0
        base = (kw_hits * 1.8) + rarity
        return max(0.0, min(10.0, base * self.weights.uniqueness_weight))

    def _quality_score(self, p: UnifiedProduct) -> float:
        premium = ["premium", "stainless", "solid", "cast iron", "ceramic", "tempered", "durable", "heavy duty", "warranty"]
        low = ["disposable", "temporary", "cheap", "budget"]
        blob = f"{p.name} {p.description}".lower()
        bonus = sum(1.0 for w in premium if w in blob)
        penalty = sum(1.0 for w in low if w in blob)
        base = 5.0 + bonus - penalty
        base *= min(1.6, max(0.6, self.weights.practicality_weight))
        return max(0.0, min(10.0, base))

    def rank(self, products: List[UnifiedProduct], limit: int = 50) -> List[ProductScore]:
        if not products:
            return []

        category_counts: Dict[str, int] = {}
        for p in products:
            for c in p.categories:
                category_counts[c] = category_counts.get(c, 0) + 1

        scored: List[ProductScore] = []
        for p in products:
            s_price = self._price_score(p)
            s_match = self._match_score(p)
            s_tech = self._tech_score(p)
            s_unique = self._uniqueness_score(p, category_counts)
            s_quality = self._quality_score(p)

            total = s_price * 0.22 + s_match * 0.33 + s_tech * 0.15 + s_unique * 0.15 + s_quality * 0.15
            scored.append(ProductScore(product=p, total_score=total, price=s_price, match=s_match, tech=s_tech, uniqueness=s_unique, quality=s_quality))

        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored[:limit]

    @staticmethod
    def cross_retailer_summary(scores: List[ProductScore]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for s in scores:
            r = s.product.retailer.value
            if r not in out:
                out[r] = {"count": 0.0, "avg_score": 0.0, "avg_price": 0.0}
            out[r]["count"] += 1.0
            out[r]["avg_score"] += s.total_score
            out[r]["avg_price"] += s.product.price
        for r, d in out.items():
            c = max(1.0, d["count"])
            d["avg_score"] /= c
            d["avg_price"] /= c
        return out

