## Present Pals — Next Generation Gift Search

This repo contains:
- A **multi-store dataset** (Best Buy + Target JSON)
- A **local TF‑IDF index pipeline** (merge → build index → query) in `src/scripts/`
- A reusable **Python backend package** in `search_engine/` that builds on that index and adds **persona + occasion-aware reranking (TODO)**

---

## Quickstart (recommended)

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

Note: `nltk` is optional but improves TF‑IDF stemming. No corpora download needed.

### 1b) Start the backend API (for the React frontend)

```bash
uvicorn api_server:app --reload --port 8000
```

Sanity check:

```bash
curl http://127.0.0.1:8000/health
```

### 2) Build merged dataset + index (local-only)

These index files are large, so you generate them locally:

```bash
python src/scripts/merge_data.py
python src/scripts/build_index.py
```

This produces:
- `src/data/products_clean.json`
- `src/index/postings.jsonl`
- `src/index/df.json`
- `src/index/doc_meta.jsonl`
- `src/index/stats.json`

### 3) Run a query

```bash
python src/scripts/query_tfidf.py --recipient mom --min_price 10 --max_price 80 --q "knife set" --k 10
```

### 4) Run tests

```bash
python -m unittest discover -s tests -v
```

---

## Frontend (Vite + React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open the Vite URL (usually `http://localhost:5173`) and submit the form.

## Repo layout

- **`src/json/`**: raw Best Buy + Target data
- **`src/scripts/`**: partner indexing pipeline
  - `merge_data.py`: build `src/data/products_clean.json`
  - `build_index.py`: build TF‑IDF artifacts in `src/index/`
  - `query_tfidf.py`: CLI TF‑IDF query with persona expansion
  - `query_cli.py`: baseline scan-based query (no index)
- **`search_engine/`**: reusable backend package
  - `merge_pipeline.py`: library wrapper of merge/clean logic
  - `tfidf_index.py`: library wrapper of TF‑IDF build/load/query
- **`tests/`**: automated tests for merge/index + integration

---

## Git workflow (team)

- Pull latest main:

```bash
git pull origin main
```

- Create a branch:

```bash
git checkout -b your-branch-name
git push --set-upstream origin your-branch-name
```

- Commit + push:

```bash
git add .
git commit -m "describe your change"
git push
```

- Open a PR on GitHub and merge after review.

