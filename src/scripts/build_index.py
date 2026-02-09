import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from nltk.stem import PorterStemmer

# Paths
SRC_DIR = Path(__file__).resolve().parent.parent  
DATA_PATH = SRC_DIR / "data" / "processed" / "products_clean.json"

INDEX_DIR = SRC_DIR / "index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

POSTINGS_PATH = INDEX_DIR / "postings.jsonl"    
DF_PATH = INDEX_DIR / "df.json"                  
DOC_META_PATH = INDEX_DIR / "doc_meta.jsonl"     
STATS_PATH = INDEX_DIR / "stats.json"            

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


# Convert text to tokens by removing stopwords, punctuations, uppercase letters etc. 
def tokenize(text: str):
    toks = TOKEN_RE.findall((text or "").lower())
    out = []
    for t in toks:
        if len(t) < 3 or t in STOPWORDS: 
            continue #remove useless words
        out.append(STEM(t))
    return out

def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Could not find products_clean.json at:\n  {DATA_PATH}\n"
            "Edit DATA_PATH in build_index.py to match your repo."
        )

    products = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(products)} products")

    # Create dictionary
    postings = defaultdict(dict)  # term -> {doc_id: tf}
    df = Counter()                # term -> df 
    N = 0

    with DOC_META_PATH.open("w", encoding="utf-8") as meta_out:
        for i, p in enumerate(products):
            # get unique id for each document
            doc_id = p.get("doc_id")
            if not doc_id:
                source = p.get("source", "unknown")
                pid = p.get("id", i)
                doc_id = f"{source}:{pid}"

            # Get text field for tokens
            text = p.get("text")
            if not text:
                name = p.get("name", "")
                desc = p.get("description", "")
                cats = " ".join([c.get("name", "") for c in p.get("categories", []) if isinstance(c, dict)])
                text = f"{name} {desc} {cats}"

            terms = tokenize(text)
            if not terms:
                continue

            tf = Counter(terms)  #get term frequencies for this document
            N += 1  #increment total number of documents in the corpus

            # update postings and df for each term in the document
            for term, freq in tf.items():
                postings[term][doc_id] = int(freq)
            # incfrement document frequency for each unique term in the document
            for term in tf.keys():
                df[term] += 1

            # metadata for UI
            category_path = p.get("category_path")
            if not category_path:
                category_path = [c.get("name", "") for c in p.get("categories", []) if isinstance(c, dict)]
                category_path = [c for c in category_path if c]

            meta = {
                "doc_id": doc_id,
                "source": p.get("source", "unknown"),
                "id": p.get("id"),
                "name": p.get("name"),
                "price": p.get("price"),
                "url": p.get("url"),
                "category_path": category_path
            }
            meta_out.write(json.dumps(meta, ensure_ascii=False) + "\n")

    DF_PATH.write_text(json.dumps(df, ensure_ascii=False), encoding="utf-8")

    with POSTINGS_PATH.open("w", encoding="utf-8") as out:
        for term in sorted(postings.keys()):
            out.write(term + "\t" + json.dumps(postings[term], ensure_ascii=False) + "\n")

    STATS_PATH.write_text(json.dumps({"N": N}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
