"""
Unified product schema used by next-gen reranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class Retailer(Enum):
    BEST_BUY = "BestBuy"
    TARGET = "Target"
    EBAY = "eBay"


@dataclass
class UnifiedProduct:
    id: str
    name: str
    price: float
    description: str
    url: str
    retailer: Retailer
    categories: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "description": self.description,
            "url": self.url,
            "retailer": self.retailer.value,
            "categories": self.categories,
        }

