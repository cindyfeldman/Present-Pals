"""
Build off partner's src/scripts/build_index.py + query_tfidf.py

This provides:
- Tokenization (optional Porter stemming if nltk available)
- Building a TF-IDF inverted index
- Saving/loading index artifacts compatible with partner scripts:
    postings.jsonl, df.json, doc_meta.jsonl, stats.json
- Querying with persona expansion (alpha core + beta expansion)

No external downloads required; if nltk isn't installed, stemming is skipped.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


try:
    from nltk.stem import PorterStemmer  # type: ignore

    _STEMMER = PorterStemmer()

    def _stem(token: str) -> str:
        return _STEMMER.stem(token)

except Exception:  # pragma: no cover

    def _stem(token: str) -> str:
        return token


TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS: Set[str] = {
    "the",
    "and",
    "or",
    "to",
    "of",
    "a",
    "an",
    "in",
    "for",
    "with",
    "on",
    "by",
    "from",
    "is",
    "it",
    "this",
    "that",
    "as",
    "at",
    "be",
    "are",
    "was",
    "were",
    "will",
    "can",
    "your",
    "you",
    "their",
    "our",
    "we",
    "they",
    "its",
    "into",
    "over",
    "up",
    "most",
    "set",
    "new",
    "all",
    "one",
    "two",
    "three",
    "each",
    "per",
    "more",
    "than",
    "not",
    "compatible",
    "design",
    "features",
    "built",
    "online",
    "expanded",
    "assortment",
    "select",
    "details",
    "includes",
    "include",
    "including",
}


def tokenize(text: str) -> List[str]:
    toks = TOKEN_RE.findall((text or "").lower())
    out: List[str] = []
    for t in toks:
        if len(t) < 3 or t in STOPWORDS:
            continue
        out.append(_stem(t))
    return out


def idf(N: int, df: int) -> float:
    return math.log((N + 1) / (df + 1)) + 1.0


def tf_weight(tf: float) -> float:
    return 1.0 + math.log(tf) if tf > 0 else 0.0


def price_ok(price: float, min_p: Optional[float], max_p: Optional[float]) -> bool:
    return (min_p is None or price >= min_p) and (max_p is None or price <= max_p)


@dataclass
class IndexPaths:
    index_dir: Path

    @property
    def postings(self) -> Path:
        return self.index_dir / "postings.jsonl"

    @property
    def df(self) -> Path:
        return self.index_dir / "df.json"

    @property
    def doc_meta(self) -> Path:
        return self.index_dir / "doc_meta.jsonl"

    @property
    def stats(self) -> Path:
        return self.index_dir / "stats.json"


@dataclass
class TfidfResult:
    doc_id: str
    final_score: float
    cosine: float
    matched_terms: List[str]


class TfidfIndex:
    """
    Disk-backed inverted index matching your partner's file formats.
    """

    def __init__(self, paths: IndexPaths):
        self.paths = paths
        self._df: Dict[str, int] = {}
        self._N: int = 0
        self._meta: Dict[str, Dict[str, Any]] = {}

    def exists(self) -> bool:
        return self.paths.postings.exists() and self.paths.df.exists() and self.paths.doc_meta.exists() and self.paths.stats.exists()

    def load(self) -> None:
        self._df = json.loads(self.paths.df.read_text(encoding="utf-8"))
        stats = json.loads(self.paths.stats.read_text(encoding="utf-8"))
        self._N = int(stats["N"])

        meta: Dict[str, Dict[str, Any]] = {}
        with self.paths.doc_meta.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                meta[obj["doc_id"]] = obj
        self._meta = meta

    @property
    def doc_count(self) -> int:
        if not self._N and self.exists():
            try:
                stats = json.loads(self.paths.stats.read_text(encoding="utf-8"))
                self._N = int(stats.get("N", 0))
            except Exception:
                return 0
        return self._N

    def build_from_docs(self, docs: Iterable[Dict[str, Any]], *, max_docs: Optional[int] = None) -> None:
        """
        Build and write the index from normalized docs (from merge_pipeline.py).
        """
        self.paths.index_dir.mkdir(parents=True, exist_ok=True)

        postings: Dict[str, Dict[str, int]] = defaultdict(dict)  # term -> {doc_id: tf}
        df = Counter()
        N = 0

        with self.paths.doc_meta.open("w", encoding="utf-8") as meta_out:
            for i, p in enumerate(docs):
                if max_docs is not None and i >= max_docs:
                    break

                doc_id = p.get("doc_id") or f"{p.get('source', 'unknown')}:{p.get('id', i)}"
                text = p.get("text") or ""
                terms = tokenize(text)
                if not terms:
                    continue

                tf = Counter(terms)
                N += 1

                for term, freq in tf.items():
                    postings[term][doc_id] = int(freq)
                for term in tf.keys():
                    df[term] += 1

                meta = {
                    "doc_id": doc_id,
                    "source": p.get("source", "unknown"),
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "price": p.get("price"),
                    "url": p.get("url"),
                    "category_path": p.get("category_path") or [],
                }
                meta_out.write(json.dumps(meta, ensure_ascii=False) + "\n")

        self.paths.df.write_text(json.dumps(df, ensure_ascii=False), encoding="utf-8")

        with self.paths.postings.open("w", encoding="utf-8") as out:
            for term in sorted(postings.keys()):
                out.write(term + "\t" + json.dumps(postings[term], ensure_ascii=False) + "\n")

        self.paths.stats.write_text(json.dumps({"N": N}, indent=2), encoding="utf-8")

        # load into memory for querying
        self.load()

    def _load_postings_for_terms(self, terms: Set[str]) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        with self.paths.postings.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                term, postings_json = line.rstrip("\n").split("\t", 1)
                if term in terms:
                    result[term] = json.loads(postings_json)
        return result

    @property
    def meta(self) -> Dict[str, Dict[str, Any]]:
        return self._meta

    def query(
        self,
        *,
        user_query: str,
        persona_terms: List[str] | None = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        k: int = 10,
        alpha_core: float = 5.0,
        beta_expansion: float = 0.6,
    ) -> List[TfidfResult]:
        """
        Return top-k doc_ids by TF-IDF cosine similarity with weighted persona expansion.
        Assisted by the partner's scripts: src/scripts/build_index.py and src/scripts/query_tfidf.py
        Math written with help from ChatGPT.
        """
        if not self._df or not self._meta or not self._N:
            self.load()

        user_tokens = tokenize(user_query or "")
        persona_tokens = tokenize(" ".join(persona_terms or []))

        if not user_tokens and not persona_tokens:
            return []

        q_tf = Counter()
        for t in user_tokens:
            q_tf[t] += alpha_core
        for t in persona_tokens:
            q_tf[t] += beta_expansion

        q_w: Dict[str, float] = {}
        q_norm_sq = 0.0
        for t, tfq in q_tf.items():
            dft = int(self._df.get(t, 0))
            if dft == 0:
                continue
            w = tf_weight(float(tfq)) * idf(self._N, dft)
            q_w[t] = w
            q_norm_sq += w * w

        if not q_w:
            return []

        q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0
        postings_map = self._load_postings_for_terms(set(q_w.keys()))

        dot = defaultdict(float)
        d_norm_sq = defaultdict(float)
        matched_terms = defaultdict(list)

        for term, postings in postings_map.items():
            dft = int(self._df.get(term, 0))
            itf = idf(self._N, dft)
            wq = q_w[term]

            for doc_id, tf in postings.items():
                wd = tf_weight(float(tf)) * itf
                dot[doc_id] += wd * wq
                d_norm_sq[doc_id] += wd * wd
                if len(matched_terms[doc_id]) < 12:
                    matched_terms[doc_id].append(term)

        user_term_set = set(user_tokens)
        ranked: List[TfidfResult] = []
        for doc_id, dp in dot.items():
            m = self._meta.get(doc_id)
            if not m:
                continue

            price = m.get("price")
            if price is None:
                continue
            if not price_ok(float(price), min_price, max_price):
                continue

            # gating: require at least one user term if user typed anything
            if user_term_set:
                if not (user_term_set & set(matched_terms.get(doc_id, []))):
                    continue

            dn = math.sqrt(d_norm_sq[doc_id]) if d_norm_sq[doc_id] > 0 else 1.0
            cosine = dp / (dn * q_norm)
            ranked.append(TfidfResult(doc_id=doc_id, final_score=cosine, cosine=cosine, matched_terms=matched_terms.get(doc_id, [])))

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        return ranked[: max(1, k)]

