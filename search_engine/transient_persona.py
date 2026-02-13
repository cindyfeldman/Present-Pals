"""
Transient Persona (recipient model) for reranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class TechProficiency(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BudgetLevel(Enum):
    LOW = "low"  # under $25
    MEDIUM = "medium"  # $25-$100
    HIGH = "high"  # $100-$500
    LUXURY = "luxury"  # $500+


@dataclass
class TransientPersona:
    interests: List[str]
    tech_proficiency: TechProficiency
    budget: BudgetLevel
    occasion: Optional[str] = None

    def get_price_range(self) -> tuple[float, float]:
        ranges = {
            BudgetLevel.LOW: (0.0, 25.0),
            BudgetLevel.MEDIUM: (25.0, 100.0),
            BudgetLevel.HIGH: (100.0, 500.0),
            BudgetLevel.LUXURY: (500.0, float("inf")),
        }
        return ranges.get(self.budget, (0.0, float("inf")))

    def get_category_preferences(self) -> List[str]:
        mapping = {
            "Gaming": ["Video Games", "Gaming Consoles", "PC Gaming", "Gaming Accessories", "Computers & Tablets"],
            "Technology": ["Computers & Tablets", "Cell Phones", "Smart Home", "Wearable Technology"],
            "Cooking": ["Kitchen & Dining", "Appliances", "Small Kitchen Appliances"],
            "Home Decor": ["Home", "Furniture", "Home Decor", "Lighting"],
            "Fitness": ["Exercise & Fitness", "Sports & Recreation", "Wearable Technology"],
            "Outdoor": ["Sports & Recreation", "Outdoor Living & Garden"],
            "Fashion": ["Clothing, Shoes & Accessories", "Jewelry", "Watches"],
            "Beauty": ["Beauty", "Health & Beauty", "Personal Care"],
            "Work": ["Office", "Computers & Tablets", "Office Electronics"],
            "Reading": ["Books", "Kindle & eReaders"],
        }
        out: List[str] = []
        for i in self.interests:
            out.extend(mapping.get(i, []))
        return list(dict.fromkeys(out))

    def tech_keywords(self) -> dict:
        return {
            TechProficiency.LOW: {
                "exclude": ["programming", "coding", "developer", "advanced", "pro", "professional", "enterprise"],
                "prefer": ["easy", "simple", "beginner", "user-friendly"],
            },
            TechProficiency.MEDIUM: {"exclude": ["developer", "enterprise"], "prefer": []},
            TechProficiency.HIGH: {"exclude": [], "prefer": ["pro", "professional", "advanced", "premium"]},
        }.get(self.tech_proficiency, {"exclude": [], "prefer": []})

    def __str__(self) -> str:
        return f"Persona(interests={self.interests}, tech={self.tech_proficiency.value}, budget={self.budget.value}, occasion={self.occasion or 'N/A'})"


class PersonaBuilder:
    @staticmethod
    def build_from_form(form_data: dict) -> TransientPersona:
        return TransientPersona(
            interests=form_data.get("interests", []),
            tech_proficiency=TechProficiency(form_data.get("tech_level", "medium")),
            budget=BudgetLevel(form_data.get("budget", "medium")),
            occasion=form_data.get("occasion"),
        )

