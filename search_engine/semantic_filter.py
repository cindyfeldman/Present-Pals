"""
Context-aware candidate filtering for reranking stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .data_harmonizer import UnifiedProduct
from .transient_persona import TransientPersona


@dataclass
class OccasionWeights:
    price_weight: float = 1.0
    uniqueness_weight: float = 1.0
    practicality_weight: float = 1.0
    preferred_categories: Optional[List[str]] = None
    excluded_categories: Optional[List[str]] = None


class OccasionContext:
    OCCASIONS: Dict[str, OccasionWeights] = {
        "birthday": OccasionWeights(
            price_weight=1.2,
            uniqueness_weight=1.3,
            practicality_weight=1.0,
            preferred_categories=["Toys & Games", "Books", "Jewelry", "Electronics", "Clothing"],
            excluded_categories=["Office", "Cleaning Supplies"],
        ),
        "wedding": OccasionWeights(
            price_weight=1.5,
            uniqueness_weight=1.4,
            practicality_weight=1.8,
            preferred_categories=["Kitchen & Dining", "Home Decor", "Appliances", "Furniture", "Bedding"],
            excluded_categories=["Gaming", "Toys", "Children"],
        ),
        "white_elephant": OccasionWeights(
            price_weight=0.5,
            uniqueness_weight=2.0,
            practicality_weight=0.3,
            preferred_categories=["Toys & Games", "Novelty", "Home Decor", "Books"],
            excluded_categories=["Jewelry"],
        ),
        "just_because": OccasionWeights(),
    }

    @staticmethod
    def get(occasion: str) -> OccasionWeights:
        key = (occasion or "just_because").lower().replace(" ", "_")
        return OccasionContext.OCCASIONS.get(key, OccasionContext.OCCASIONS["just_because"])


class SemanticFilter:
    def __init__(self, persona: TransientPersona):
        self.persona = persona
        self.weights = OccasionContext.get(persona.occasion or "just_because")

    def apply(self, products: List[UnifiedProduct], *, verbose: bool = False) -> List[UnifiedProduct]:
        lo, hi = self.persona.get_price_range()
        out = [p for p in products if lo <= p.price <= hi]

        # category intent
        preferred = list(self.persona.get_category_preferences())
        if self.weights.preferred_categories:
            preferred.extend(self.weights.preferred_categories)
        preferred_l = [c.lower() for c in preferred]

        excluded = [c.lower() for c in (self.weights.excluded_categories or [])]

        filtered: List[UnifiedProduct] = []
        for p in out:
            cats = " ".join(p.categories).lower()
            if excluded and any(e in cats for e in excluded):
                continue
            if preferred_l:
                if any(pc in cats for pc in preferred_l):
                    filtered.append(p)
            else:
                filtered.append(p)

        # tech constraint
        kw = self.persona.tech_keywords()
        ex = kw.get("exclude", [])
        if ex:
            final: List[UnifiedProduct] = []
            for p in filtered:
                blob = f"{p.name} {p.description}".lower()
                if any(w in blob for w in ex):
                    continue
                final.append(p)
            filtered = final

        if verbose:
            print(f"Filtered to {len(filtered)} candidates")
        return filtered

    def stats(self) -> Dict[str, Any]:
        return {"persona": str(self.persona), "occasion": self.persona.occasion, "price_range": self.persona.get_price_range()}

