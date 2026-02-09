
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------- Paths (robust) ----------------
SRC_DIR = Path(__file__).resolve().parent.parent  # .../src
DATA_PATH = SRC_DIR / "data" / "processed" / "products_clean.json"
PERSONA_PATH = SRC_DIR / "config" / "personas.json"

# ---------------- Tokenization ----------------
TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "the","and","or","to","of","a","an","in","for","with","on","by","from","is","it","this","that",
    "as","at","be","are","was","were","will","can","your","you","their","our","we","they","its",
    "into","over","up","most","set","new","all","one","two","three","each","per","more","than","not",
    "about","these","those","includes","include","including","feature","features","design","compatible",
    "online","expanded","assortment","select","details"
}

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    toks = TOKEN_RE.findall(text.lower())
    return [t for t in toks if len(t) >= 3 and t not in STOPWORDS]

# ---------------- Persona/category mapping ----------------
# Use top-level categories in your dataset to compute a persona boost.
# You can refine this later as you learn more.
PERSONA_TOPLEVEL_CATS = {
    "dad": {"Audio", "Car Electronics & GPS", "Computers & Tablets", "Fitness & GPS Watches", "Sports & Outdoors", "Video Games"},
    "mom": {"Home", "Kitchen & Dining", "Beauty", "Personal Care", "Furniture", "Furniture & Decor", "Outdoor Living & Garden"},
    "sister": {"Beauty", "Personal Care", "Clothing, Shoes & Accessories", "Home", "Furniture & Decor"},
    "brother": {"Video Games", "Audio", "Computers & Tablets", "Car Electronics & GPS", "Fitness & GPS Watches", "Sports & Outdoors"},
    "for him": {"Clothing, Shoes & Accessories", "Audio", "Car Electronics & GPS", "Video Games", "Computers & Tablets", "Sports & Outdoors"},
    "for her": {"Clothing, Shoes & Accessories", "Beauty", "Personal Care", "Home", "Furniture & Decor", "Kitchen & Dining"},
    "friend": {"Grocery", "Home", "Kitchen & Dining", "Audio", "Video Games", "Toys, Games & Drones", "Beauty", "Personal Care"}
}

def get_top_level_category(product: dict) -> str:
    path = product.get("category_path") or []
    return path[0] if path else "UNKNOWN"

# ---------------- Scoring ----------------
def overlap_score(query_tokens: List[str], doc_tokens: List[str]) -> int:
    """Simple keyword overlap (counts how many query tokens appear in doc tokens)."""
    doc_set = set(doc_tokens)
    return sum(1 for qt in query_tokens if qt in doc_set)

def persona_boost(recipient: str, top_level_cat: str) -> float:
    """Boost if product's top-level category matches persona preferences."""
    if not recipient:
        return 0.0
    if recipient not in PERSONA_TOPLEVEL_CATS:
        return 0.0
    return 2.0 if top_level_cat in PERSONA_TOPLEVEL_CATS[recipient] else 0.0

def price_ok(price: float, min_p: float, max_p: float) -> bool:
    return (min_p is None or price >= min_p) and (max_p is None or price <= max_p)

# ---------------- Main ----------------
def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description="Gift recommender baseline CLI search (no index).")
    parser.add_argument("--recipient", type=str, default="",
                        help="Recipient type: mom, dad, sister, brother, for him, for her, friend")
    parser.add_argument("--min_price", type=float, default=None, help="Minimum price (inclusive)")
    parser.add_argument("--max_price", type=float, default=None, help="Maximum price (inclusive)")
    parser.add_argument("--q", type=str, default="", help="Free-text query (optional)")
    parser.add_argument("--k", type=int, default=10, help="Number of results to show")
    parser.add_argument("--max_scan", type=int, default=20000,
                        help="Max products to scan (useful if your dataset is huge; 0 = scan all)")
    args = parser.parse_args()

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_PATH}")
    if not PERSONA_PATH.exists():
        raise FileNotFoundError(f"Missing personas file: {PERSONA_PATH}")

    products = load_json(DATA_PATH)
    personas: Dict[str, List[str]] = load_json(PERSONA_PATH)

    recipient = (args.recipient or "").strip().lower()

    # -------- Query expansion --------
    user_query = args.q.strip()
    persona_terms = personas.get(recipient, []) if recipient else []
    expanded_query = " ".join([user_query, " ".join(persona_terms)]).strip()

    q_tokens = tokenize(expanded_query)

    print("\n=== Gift Search (Baseline) ===")
    print(f"Recipient: {recipient if recipient else '(none)'}")
    print(f"Budget: {args.min_price if args.min_price is not None else '-inf'} .. {args.max_price if args.max_price is not None else '+inf'}")
    print(f"User query: {user_query if user_query else '(none)'}")
    print(f"Expanded query: {expanded_query if expanded_query else '(none)'}")
    print(f"Query tokens ({len(q_tokens)}): {q_tokens[:20]}{'...' if len(q_tokens) > 20 else ''}\n")

    # -------- Scan + score --------
    results: List[Tuple[float, dict, dict]] = []  # (final_score, product, explanation)
    scanned = 0
    kept_after_price = 0

    for p in products:
        scanned += 1
        if args.max_scan and args.max_scan > 0 and scanned > args.max_scan:
            break

        price = p.get("price")
        if price is None:
            continue
        if not price_ok(price, args.min_price, args.max_price):
            continue
        kept_after_price += 1

        doc_text = p.get("text", "")  # combined field from your normalization script
        doc_tokens = tokenize(doc_text)

        base = overlap_score(q_tokens, doc_tokens) if q_tokens else 0

        top_cat = get_top_level_category(p)
        boost = persona_boost(recipient, top_cat)

        # Slight preference for having a description (helps quality)
        has_desc = 1.0 if (p.get("description") or "").strip() else 0.0

        # Weighted final score (tweakable)
        final = base + boost + 0.2 * has_desc

        # Build explanation
        matched = []
        if q_tokens:
            doc_set = set(doc_tokens)
            matched = [t for t in q_tokens if t in doc_set][:8]  # show up to 8
        why = {
            "base_overlap": base,
            "persona_boost": boost,
            "top_level_category": top_cat,
            "matched_terms": matched,
            "has_description_bonus": 0.2 * has_desc
        }

        results.append((final, p, why))

    # -------- Sort + display --------
    results.sort(key=lambda x: x[0], reverse=True)
    topk = results[: max(args.k, 1)]

    print(f"Scanned: {scanned} products")
    print(f"After price filter: {kept_after_price} products")
    print(f"Returning top {len(topk)} results:\n")

    if not topk:
        print("No results found. Try widening budget or adding a query.")
        return

    for rank, (score, p, why) in enumerate(topk, start=1):
        title = p.get("name") or "(no name)"
        price = p.get("price")
        source = p.get("source", "unknown")
        url = p.get("url", "")

        # Build the human explanation line
        persona_reason = ""
        if recipient:
            if why["persona_boost"] > 0:
                persona_reason = f"matches {recipient} via category '{why['top_level_category']}'"
            else:
                persona_reason = f"category '{why['top_level_category']}' (no {recipient} boost)"

        matched_terms = why["matched_terms"]
        matched_reason = f"matched terms: {matched_terms}" if matched_terms else "matched terms: (none)"

        print(f"{rank}. {title}")
        print(f"   ${price:.2f} | {source} | score={score:.2f}")
        print(f"   why: {matched_reason}; {persona_reason}")
        if url:
            print(f"   url: {url}")
        print()

if __name__ == "__main__":
    main()
