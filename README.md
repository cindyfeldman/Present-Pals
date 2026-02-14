## Present Pals — Next Generation Gift Search

This repo contains:
- A **multi-store dataset** (Best Buy + Target JSON)
- A **local TF‑IDF index pipeline** (merge → build index → query) in `src/scripts/`
- A reusable **Python backend package** in `search_engine/` that builds on that index and adds **persona + occasion-aware reranking (TODO)**

---

## Quickstart (Demo-safe)

### 1) Install Python dependencies

```bash
pip install -r requirements.txt
```

No extra `nltk` corpora download is needed.

### 2) Start backend API (Terminal A)

```bash
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

Sanity check:

```bash
curl http://127.0.0.1:8000/health
```

### 3) Build merged dataset + index (one-time local setup)

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

### 4) Run a CLI query (optional sanity check)

```bash
python src/scripts/query_tfidf.py --recipient mom --min_price 10 --max_price 80 --q "knife set" --k 10
```

### 5) Run tests

```bash
python -m unittest discover -s tests -v
```

---

## Frontend (Vite + React, Terminal B)

In a second terminal:

```bash
cd frontend
nvm use
npm install
npm run dev
```

Then open the Vite URL (usually `http://localhost:5173`) and submit the form.

---

## Common demo errors (and fixes)

### 1) `npm ... not to run on Node.js v14`

You are on old Node. Switch to Node 20:

```bash
cd frontend
nvm install 20
nvm use 20
node -v
npm -v
```

Then rerun:

```bash
npm install
npm run dev
```

### 2) Frontend says `Failed to fetch recommendations`

Usually backend is not running, or wrong host/port.

Check backend:

```bash
curl http://127.0.0.1:8000/health
```

If it fails, restart backend:

```bash
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

### 3) `/search` returns 404 on localhost:8000

Port 8000 may be used by another service (often Docker on IPv6).  
Use `127.0.0.1` for backend/proxy target (already configured in Vite).

Check listeners:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

### 4) You changed `vite.config.js` but proxy still behaves old

Vite must be restarted after config changes:

```bash
# in frontend terminal
Ctrl+C
npm run dev
```

### 5) `git switch main` blocked by local changes

Commit or stash first:

```bash
git add .
git commit -m "wip"
# or: git stash
git switch main
```

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

