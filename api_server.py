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
from curl_cffi.requests import AsyncSession
import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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

# Define cache directory
CACHE_DIR = REPO_ROOT / "image_cache"
CACHE_DIR.mkdir(exist_ok=True)


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


def _needs_merge_rebuild(out_path: Path, inputs: List[Path]) -> bool:
    if not out_path.exists():
        return True
    out_mtime = out_path.stat().st_mtime
    for p in inputs:
        if p.exists() and p.stat().st_mtime > out_mtime:
            return True
    return False


def _needs_index_rebuild(idx: TfidfIndex, merged_path: Path) -> bool:
    if not idx.exists():
        return True
    merged_mtime = merged_path.stat().st_mtime
    index_files = [idx.paths.postings, idx.paths.df, idx.paths.doc_meta, idx.paths.stats]
    for p in index_files:
        if not p.exists() or p.stat().st_mtime < merged_mtime:
            return True
    return False


def _ensure_data_and_index() -> None:
    global _index, _meta, _personas

    additional_sources = {
        "amazon": RAW_AMAZON_CSV,
        "walmart": RAW_WALMART_CSV,
    }
    source_paths = [RAW_BESTBUY, RAW_TARGET] + [p for p in additional_sources.values()]

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
    if _needs_index_rebuild(idx, MERGED_PATH):
        docs = json.loads(MERGED_PATH.read_text(encoding="utf-8"))
        idx.build_from_docs(docs)
    else:
        idx.load()

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

# Helper to clean up old images
def cleanup_cache():
    import time
    now = time.time()
    for f in CACHE_DIR.iterdir():
        if f.stat().st_mtime < now - (3 * 86400): # 3 days
            f.unlink()


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

# Helper function to get images from Amazon
async def get_amazon_image(soup, html_text):
    
    match = re.search(r'"hiRes":"(https://.*?\.jpg)"', html_text)
    if match: return match.group(1)
    img = soup.find("img", id="landingImage")
    return img.get("src") if img else None

# Helper function to get images from Best Buy
async def get_bestbuy_image(soup, html_text):
    img = soup.find("img", class_="primary-image")
    if img: return img.get("src")
    link = soup.find("link", rel="image_src")
    return link.get("href") if link else None

# Helper function to get images from Walmart
async def get_walmart_image(soup, html_text):
    # Standard Meta Tag
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        return meta.get("content")

    # JSON-LD (Search for the "Image" type)
    json_ld = soup.find("script", type="application/ld+json")
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            if isinstance(data, list): data = data[0]
            img = data.get("image")
            if isinstance(img, list): return img[0]
            if img: return img
        except:
            pass

    # The "__NEXT_DATA__" (Walmart also uses Next.js)
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.string)
            # Deep path for Walmart's image assets
            img = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {}).get("product", {}).get("imageAssets", [{}])[0].get("url")
            if img: return img
        except:
            pass
            
    return None

# Helper function to get images from Target
async def get_target_image(soup, html_text):
    # Parse the __NEXT_DATA__ JSON blob
    target_data = soup.find("script", id="__NEXT_DATA__")
    if target_data:
        try:
            data = json.loads(target_data.string)
            # This path is deep, so we use .get() safely
            product = data.get("props", {}).get("pageProps", {}).get("product", {})
            img_url = product.get("item", {}).get("enrichment", {}).get("images", {}).get("primary_image_url")
            if img_url:
                return img_url
        except:
            pass
    
    # Fallback: OpenGraph (Target sometimes populates this for social sharing)
    meta = soup.find("meta", property="og:image")
    return meta.get("content") if meta else None

@app.get("/proxy-image")
async def proxy_image(product_url: str, background_tasks: BackgroundTasks):
    try: 
        # Hash the URL to create a unique cache filename
        url_hash = hashlib.md5(product_url.encode()).hexdigest()
        cache_path = CACHE_DIR / f"{url_hash}.jpg"

        if cache_path.exists():
            return FileResponse(cache_path)
		
        headers = {
            # 1. The Identity: Claims we are a standard Windows 10 Chrome user
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        
            # 2. The Content: Tells the server what file types we can handle
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        
            # 3. Client Hints: CRITICAL for Chrome impersonation
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        
            # 4. Fetch Metadata: Tells the server how we navigated to the page
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        
            # 5. Behavior: Standard browser "upkeep" headers
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }

		# Determine settings based on domain
        domain = ""
        if "amazon.com" in product_url: domain = "amazon"
        elif "bestbuy.com" in product_url: domain = "bestbuy"
        elif "target.com" in product_url: domain = "target"
        elif "walmart.com" in product_url: domain = "walmart"

		# Best Buy and Target often prefer HTTP/1.1 to avoid stream resets
        use_http2 = False if domain in ["bestbuy", "target"] else True
		
        async with AsyncSession(impersonate="chrome") as session:
            current_headers = headers.copy()
			#Add a Referer specific to the store
            if domain:
                current_headers["Referer"] = f"https://www.{domain}.com/"
				
            resp = await session.get(product_url, headers=current_headers, timeout=15)
			
			# Check if we got a valid page back
            if resp.status_code != 200:
                return {"error": f"Site returned status {resp.status_code}"}
			
            soup = BeautifulSoup(resp.text, 'html.parser')
            actual_img_url = None
			
			# Dispatch to the correct helper
            if domain == "amazon":
                actual_img_url = await get_amazon_image(soup, resp.text)
            elif domain == "bestbuy":
                actual_img_url = await get_bestbuy_image(soup, resp.text)
            elif domain == "target":
                actual_img_url = await get_target_image(soup, resp.text)
            elif domain == "walmart":
                actual_img_url = await get_walmart_image(soup, resp.text)
            else:
				# Generic fallback for eBay or others
                meta = soup.find("meta", property="og:image")
                actual_img_url = meta.get("content") if meta else None
				

            if not actual_img_url:
                return {"error": f"Could not extract image URL from {domain or 'site'}"}

			# CLEAN IMAGE URL 
            if actual_img_url:
                actual_img_url = urljoin(product_url, actual_img_url)
                if "amazon.com" in product_url: # Only run Amazon-specific cleaning on Amazon links
                    actual_img_url = re.sub(r'\._AC_.*?\.', '.', actual_img_url)

			# DOWNLOAD THE IMAGE
            img_response = await session.get(actual_img_url, headers=headers)
				
            if img_response.status_code != 200:
                return {"error": "Failed to fetch image file"}

            if "image" not in img_response.headers.get("Content-Type", "").lower():
                return {"error": "URL did not point to a valid image"}

            with open(cache_path, "wb") as f:
                f.write(img_response.content)
				
            return FileResponse(cache_path)
    
    except Exception as e:
        # This catches any other weird errors and returns them as JSON instead of a 500
        return {"error": "Internal Server Error", "details": str(e)}

