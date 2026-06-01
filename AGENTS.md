# AGENTS.md

## Setup & Run

```bash
# Install deps (no requirements.txt, no package manager)
pip install python-dotenv requests feedparser beautifulsoup4 parsel cloakbrowser "cloakbrowser[geoip]" pyyaml python-dateutil
pip install sentence-transformers  # optional, for Phase D

# Run (must be from project root - no `__init__.py` in src/, no package install)
python src/main.py                   # desktop with display
xvfb-run -a python src/main.py      # headless server (cloakbrowser uses headful Chromium)

# Config self-test: python src/config.py
```

## Tests

```bash
pytest tests/ -v                    # all tests
pytest tests/ -v -k "not pdf"       # skip PDF tests (needs pandoc + xelatex)
pytest tests/test_db.py -v          # single module
```

No lint, formatter, or typechecker is configured.

## Reset Pipeline

```bash
# Reset semantic judgments + downstream (after updating domain_description/keywords)
python tools/reset_pipeline.py reset-semantic
python tools/reset_pipeline.py reset-semantic --publisher aps

# Retry failed publisher scrapes (Phase C)
python tools/reset_pipeline.py reset-publisher
python tools/reset_pipeline.py reset-publisher --publisher aps

# Retry failed MinerU PDF parsing (Phase E2)
python tools/reset_pipeline.py reset-mineru
python tools/reset_pipeline.py reset-mineru --publisher aps

# Retry failed LLM summaries (Phase F)
python tools/reset_pipeline.py reset-summary
python tools/reset_pipeline.py reset-summary --publisher aps

# Reset report status (Phase G) — re-include papers in next report
python tools/reset_pipeline.py reset-report
python tools/reset_pipeline.py reset-report --publisher aps
```

Scripts prompt for confirmation before executing; prints affected row count.

## Architecture

- **Not a package** — `src/` has no `__init__.py`. All imports resolve relative to project root at runtime. Run scripts from repo root.
- **8-phase pipeline** in `src/main.py`: RSS → CrossRef → Publisher (cloakbrowser) → Semantic Filter (D) → LLM Relevance (E) → MinerU PDF (E2) → LLM Summary (F) → Report → Email.
- **Phase D gates Phase E** — papers scoring below `SEMANTIC_SIMILARITY_THRESHOLD` (0.3) are marked irrelevant and skip the LLM phase entirely (saves API costs).
- **cloakbrowser uses headful Chromium** — Cloudflare bypass requires a visible browser. cloakbrowser handles browser fingerprinting automatically. Use `xvfb-run -a` on headless servers.
- **Publisher scrapers** (`src/sources/publisher.py`) are per-publisher classes. Each publisher gets a persistent browser context with `headless=False` and 2–30s random delays between pages.

## Config & Secrets

- API keys and tokens loaded via `python-dotenv` from `.env` file (DeepSeek, CrossRef, MinerU JWT).
- Email credentials in `configs/email.yaml`.
- **Do not commit credential files.** They contain real secrets.
- Keywords: `configs/keywords.yaml` — Chinese and English terms for laser plasma physics.

## Dependencies / Models

- `sentence-transformers` model (`all-MiniLM-L6-v2`) must be in `data/models/all-MiniLM-L6-v2/`. Loaded with `local_files_only=True`. Download manually before first run.
- `sqlite3` database at `data/papers.db` — one table (`papers`) with per-phase status columns. All pipeline state persists here; restart is safe.
- Report output goes to `data/reports/` (Markdown format).

## Language

All comments, docstrings, prompts, and report text are in Chinese. Generated reports are in Chinese.
