import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

from nltk.stem import PorterStemmer

# File paths
SRC_DIR = Path(__file__).resolve().parent.parent
INDEX_DIR = SRC_DIR / "index"

POSTINGS_PATH = INDEX_DIR / "postings.jsonl"
DF_PATH = INDEX_DIR / "df.json"
DOC_META_PATH = INDEX_DIR / "doc_meta.jsonl"
STATS_PATH = INDEX_DIR / "stats.json"

PERSONA_PATH = SRC_DIR / "config" / "personas.json"

# Tokenization / Stemming 
TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "the","and","or","to","of","a","an","in","for","with","on","by","from","is","it","this","that",
    "as","at","be","are","was","were","will","can","your","you","their","our","we","they","its",
    "into","over","up","most","set","new","all","one","two","three","each","per","more","than","not",
    "compatible","design","features","built","online","expanded","assortment","select","details",
    "includes","include","including"
}

#use STEM to normalize meaninful word forms to their root form 
STEM = PorterStemmer().stem

# Convert query words to tokens by removing stopwords, punctuations, uppercase letters etc. 
def tokenize(text: str) -> List[str]:
    toks = TOKEN_RE.findall((text or "").lower())
    out = []
    for t in toks:
        if len(t) < 3 or t in STOPWORDS:
            continue
        out.append(STEM(t))
    return out

# TF-IDF helpers
# More important words have higher idf. We add 1 to avoid zero division
def idf(N: int, df: int) -> float:
    return math.log((N + 1) / (df + 1)) + 1.0

# Weighted term frequency. Repeated words count more, but not linearly. 
def tf_weight(tf: float) -> float:
    return 1.0 + math.log(tf) if tf > 0 else 0.0

# Checks if the price is within user specified budget
def price_ok(price: float, min_p: float, max_p: float) -> bool:
    return (min_p is None or price >= min_p) and (max_p is None or price <= max_p)

# Loads each line from doc_meta.jsonl into a dictionary:
def load_doc_meta(path: Path) -> Dict[str, dict]:
    meta = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                meta[obj["doc_id"]] = obj
    return meta

# Loads postings for the given set of terms into a dictionary
def load_postings_for_terms(terms: set) -> Dict[str, Dict[str, int]]:
    result = {}
    with POSTINGS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            term, postings_json = line.rstrip("\n").split("\t", 1)
            if term in terms:
                result[term] = json.loads(postings_json)
    return result



def main():
    # Parse user input (CLI for now)
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", default="", type=str)
    parser.add_argument("--min_price", default=None, type=float)
    parser.add_argument("--max_price", default=None, type=float)
    parser.add_argument("--q", default="", type=str)
    parser.add_argument("--k", default=10, type=int)
    args = parser.parse_args()

    for p in [POSTINGS_PATH, DF_PATH, DOC_META_PATH, STATS_PATH]:
        if not p.exists():
            raise FileNotFoundError(f"Missing {p}. Run: python src/scripts/build_index.py")

    df = json.loads(DF_PATH.read_text(encoding="utf-8"))
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    meta = load_doc_meta(DOC_META_PATH)
    personas = json.loads(PERSONA_PATH.read_text(encoding="utf-8")) if PERSONA_PATH.exists() else {}

    N = int(stats["N"])
    recipient = (args.recipient or "").strip().lower()

    # Weighted query expansion using personas. User query terms are weighted more than persona hints, but both contribute to the final query vector.
    # Get user query tokens
    user_query = (args.q or "").strip()
    user_tokens = tokenize(user_query)

    # Get persona hint tokens
    persona_terms = personas.get(recipient, []) if recipient else []
    persona_tokens = tokenize(" ".join(persona_terms))

    if not user_tokens and not persona_tokens:
        print("No query tokens. Try: --q \"knife\"")
        return

    # User intent dominates persona hints
    ALPHA_CORE = 5.0   # strong
    BETA_EXP = 0.6     # light

    q_tf = Counter()
    for t in user_tokens:
        q_tf[t] += ALPHA_CORE
    for t in persona_tokens:
        q_tf[t] += BETA_EXP

    # Build tf-idf query vector
    q_w = {}
    q_norm_sq = 0.0
    for t, tfq in q_tf.items():
        dft = int(df.get(t, 0))
        if dft == 0:
            continue
        w = tf_weight(float(tfq)) * idf(N, dft)
        q_w[t] = w
        q_norm_sq += w * w

    if not q_w:
        print("No query terms found in vocabulary (after stemming). Try a different query.")
        return

    q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0
    needed_terms = set(q_w.keys())
    # Load postings for only the terms in this query
    postings_map = load_postings_for_terms(needed_terms)

    # Retrieval + scoring 
    dot = defaultdict(float)
    d_norm_sq = defaultdict(float)
    matched_terms = defaultdict(list)

    for term, postings in postings_map.items():
        dft = int(df.get(term, 0))
        itf = idf(N, dft)
        wq = q_w[term]

        for doc_id, tf in postings.items():
            wd = tf_weight(float(tf)) * itf  # TF-IDF weight for doc term
            dot[doc_id] += wd * wq
            d_norm_sq[doc_id] += wd * wd
            if len(matched_terms[doc_id]) < 10:
                matched_terms[doc_id].append(term)

    # Intent gating: require at least one *core user* term to match
    # If user didn't type anything (only persona), skip gating.
    user_term_set = set(user_tokens)

    # Apply boosts and fiters and get final score
    ranked = []
    for doc_id, dp in dot.items():
        m = meta.get(doc_id)
        if not m:
            continue
        
        # budget filter
        price = m.get("price")
        if price is None:
            continue
        if not price_ok(float(price), args.min_price, args.max_price):
            continue

        # must match at least one user term
        if user_term_set:
            if not (user_term_set & set(matched_terms.get(doc_id, []))):
                continue

        # Compute cosine similarity
        dn = math.sqrt(d_norm_sq[doc_id]) if d_norm_sq[doc_id] > 0 else 1.0
        cosine = dp / (dn * q_norm)

        top_cat = (m.get("category_path") or ["UNKNOWN"])[0]
        final_score = cosine  
        ranked.append((final_score, cosine, doc_id))

    ranked.sort(reverse=True, key=lambda x: x[0])
    topk = ranked[: max(1, args.k)]

    # Print results 
    expanded_preview = user_query
    if recipient and recipient in personas and personas[recipient]:
        expanded_preview = (user_query + " " + " ".join(personas[recipient])).strip()

    print("\n=== TF-IDF Gift Search ===")
    print(f"Recipient: {recipient if recipient else '(none)'}")
    print(f"Budget: {args.min_price if args.min_price is not None else '-inf'} .. {args.max_price if args.max_price is not None else '+inf'}")
    print(f"User query: {user_query if user_query else '(none)'}")
    print(f"Expanded query: {expanded_preview}")

    if not topk:
        print("\nNo results found. (Try widening budget or different words.)")
        return

    print(f"\nTop {len(topk)} results:\n")
    for i, (final_score, cosine, doc_id) in enumerate(topk, start=1):
        m = meta[doc_id]
        name = m.get("name", "(no name)")
        price = float(m.get("price", 0.0))
        source = m.get("source", "unknown")
        url = m.get("url", "")
        top_cat = (m.get("category_path") or ["UNKNOWN"])[0]

        # Explanation
        matched = matched_terms.get(doc_id, [])
        core_matches = sorted(list(set(matched) & user_term_set)) if user_term_set else []
        persona_matches = sorted(list(set(matched) - set(core_matches)))

        print(f"{i}. {name}")
        print(f"   ${price:.2f} | {source} | final={final_score:.4f} (cosine={cosine:.4f}) | {top_cat}")
        if core_matches:
            print(f"   why: matched your query terms: {core_matches[:8]}")
        if persona_matches:
            print(f"        also matched persona hints: {persona_matches[:8]}")
        if url:
            print(f"   url: {url}")
        print()
        
# Function to be called by FastAPI, returns top-k results as JSON instead of printing
def get_recommendations(recipient="", min_price=None, max_price=None, q="", k=10):
    # same logic as main()
    for p in [POSTINGS_PATH, DF_PATH, DOC_META_PATH, STATS_PATH]:
        if not p.exists():
            raise FileNotFoundError(f"Missing {p}. Run: python src/scripts/build_index.py")

    df = json.loads(DF_PATH.read_text(encoding="utf-8"))
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    meta = load_doc_meta(DOC_META_PATH)
    personas = json.loads(PERSONA_PATH.read_text(encoding="utf-8")) if PERSONA_PATH.exists() else {}

    N = int(stats["N"])
    recipient = (recipient or "").strip().lower()

    # Weighted query expansion using personas. User query terms are weighted more than persona hints, but both contribute to the final query vector.
    # Get user query tokens
    user_query = (q or "").strip()
    user_tokens = tokenize(user_query)

    # Get persona hint tokens
    persona_terms = personas.get(recipient, []) if recipient else []
    persona_tokens = tokenize(" ".join(persona_terms))

    if not user_tokens and not persona_tokens:
        print("No query tokens. Try: --q \"knife\"")
        return

    # User intent dominates persona hints
    ALPHA_CORE = 5.0   # strong
    BETA_EXP = 0.6     # light

    q_tf = Counter()
    for t in user_tokens:
        q_tf[t] += ALPHA_CORE
    for t in persona_tokens:
        q_tf[t] += BETA_EXP

    # Build tf-idf query vector
    q_w = {}
    q_norm_sq = 0.0
    for t, tfq in q_tf.items():
        dft = int(df.get(t, 0))
        if dft == 0:
            continue
        w = tf_weight(float(tfq)) * idf(N, dft)
        q_w[t] = w
        q_norm_sq += w * w

    if not q_w:
        print("No query terms found in vocabulary (after stemming). Try a different query.")
        return

    q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0
    needed_terms = set(q_w.keys())
    # Load postings for only the terms in this query
    postings_map = load_postings_for_terms(needed_terms)

    # Retrieval + scoring 
    dot = defaultdict(float)
    d_norm_sq = defaultdict(float)
    matched_terms = defaultdict(list)

    for term, postings in postings_map.items():
        dft = int(df.get(term, 0))
        itf = idf(N, dft)
        wq = q_w[term]

        for doc_id, tf in postings.items():
            wd = tf_weight(float(tf)) * itf  # TF-IDF weight for doc term
            dot[doc_id] += wd * wq
            d_norm_sq[doc_id] += wd * wd
            if len(matched_terms[doc_id]) < 10:
                matched_terms[doc_id].append(term)

    # Intent gating: require at least one *core user* term to match
    # If user didn't type anything (only persona), skip gating.
    user_term_set = set(user_tokens)

    # Apply boosts and fiters and get final score
    ranked = []
    for doc_id, dp in dot.items():
        m = meta.get(doc_id)
        if not m:
            continue
        
        # budget filter
        price = m.get("price")
        if price is None:
            continue
        if not price_ok(float(price), min_price, max_price):
            continue

        # must match at least one user term
        if user_term_set:
            if not (user_term_set & set(matched_terms.get(doc_id, []))):
                continue

        # Compute cosine similarity
        dn = math.sqrt(d_norm_sq[doc_id]) if d_norm_sq[doc_id] > 0 else 1.0
        cosine = dp / (dn * q_norm)

        top_cat = (m.get("category_path") or ["UNKNOWN"])[0]
        final_score = cosine  
        ranked.append((final_score, cosine, doc_id))

    ranked.sort(reverse=True, key=lambda x: x[0])
    topk = ranked[: max(1, k)]
    
	# Instead of printing at the end, build a list of results
    results = []
    for i, (final_score, cosine, doc_id) in enumerate(topk, start=1):
        m = meta[doc_id]
        
        # Build a clean dictionary for React to read
        results.append({
            "id": doc_id,
            "name": m.get("name", "(no name)"),
            "price": float(m.get("price", 0.0)),
            "source": m.get("source", "unknown"),
            "url": m.get("url", ""),
            "category": (m.get("category_path") or ["UNKNOWN"])[0],
            "score": round(float(final_score), 4),
            "matches": matched_terms.get(doc_id, [])
        })
    
    return results

if __name__ == "__main__":
    main()
