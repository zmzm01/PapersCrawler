# AGENTS.md

## Setup & Run

```bash
pip install python-dotenv requests feedparser beautifulsoup4 parsel \
            cloakbrowser "cloakbrowser[geoip]" pyyaml python-dateutil
pip install sentence-transformers  # optional — only Phase D needs it

cp .env.example .env               # fill in CROSSREF_MAILTO, MINERU_TOKEN, DEEPSEEK_API_KEY
python src/config.py                # self-test: prints loaded journal config

python src/main.py                  # desktop
xvfb-run -a python src/main.py     # headless (cloakbrowser needs headful Chromium)
```

## Tests

```bash
pytest tests/ -v                          # all tests
pytest tests/ -v -k "not pdf"             # skip PDF tests (needs pandoc + xelatex)
pytest tests/test_db.py -v                # single module
```

Tests with `network`, `slow`, or `browser` markers are **skipped by default** (see `tests/conftest.py:13-23`). To run them, pass `-m`:

```bash
pytest tests/ -m network                  # enable network-dependent tests
```

No lint, formatter, or typechecker is configured.

## Phase Switching

All 8 phases can be toggled in `src/config.py:168-176` via `SKIP_PHASE_A` … `SKIP_PHASE_H`. Default (debug/dev) skips A–E, E2, H; only runs F+G. Set `MAX_PAPERS_PER_PHASE = 0` for unlimited.

## Pipeline Reset

```bash
python tools/reset_pipeline.py reset-semantic   # Phase D + downstream (after keyword changes)
python tools/reset_pipeline.py reset-publisher  # retry failed Phase C scrapes
python tools/reset_pipeline.py reset-mineru     # retry failed Phase E2 PDF parsing
python tools/reset_pipeline.py reset-summary    # retry failed Phase F summaries
python tools/reset_pipeline.py reset-report     # re-include papers in next Phase G report
```

All support `--publisher aps` to filter. Each prints SQL + row count and prompts `[y/N]` before executing.

Other debug tools: `tools/debug_llm_summary.py`, `tools/debug_publisher_urls.py`, `tools/reset_empty_abstract.py`.

## Architecture

- **Not a package** — `src/` has **no** `__init__.py`. All imports resolve relative to project root at runtime.
- **8 phases** in `src/main.py`: RSS → CrossRef → Publisher (cloakbrowser) → Semantic Filter → LLM Relevance → MinerU PDF → LLM Summary → Report → Email.
- **Phase D gates Phase E** — papers below `SEMANTIC_SIMILARITY_THRESHOLD` (0.3, in `src/config.py:158`) skip LLM, saving API costs.
- **Publisher scrapers** (`src/sources/publisher.py`): per-publisher class with persistent browser context, `headless=False`, 2–30s random page delays, 3-consecutive-failure circuit breaker.
- **Optica** needs proxy (`http://127.0.0.1:10808`, configurable in `src/config.py:197-199`); Optica journals are also `enabled: false` by default in `configs/publishers.yaml`.
- **Nature News** is filtered out via `SKIP_NATURE_NEWS` (looks for `/d41586-` in DOI prefix).

## Config & Secrets

| File | Content |
|------|---------|
| `.env` | `CROSSREF_MAILTO`, `MINERU_TOKEN`, `DEEPSEEK_API_KEY` (gitignored) |
| `configs/email.yaml` | SMTP creds + recipients (gitignored) |
| `configs/keywords.yaml` | Chinese + English keywords/domain description for laser-plasma physics |
| `configs/publishers.yaml` | Journal RSS feeds + `enabled` flags |

## Data Layout

All under `data/` (gitignored; first run creates it):

| Path | Usage |
|------|-------|
| `papers.db` | SQLite — single `papers` table with per-phase status columns |
| `reports/` | Markdown report output |
| `models/all-MiniLM-L6-v2/` | sentence-transformers model (must be downloaded manually first; loaded with `local_files_only=True`) |
| `session_cached/` | Per-publisher cloakbrowser persistent browser contexts |
| `mineru_output/` | MinerU PDF parse results (one subdir per sanitised DOI) |

## Language

All comments, docstrings, LLM prompts, and generated reports are in **Chinese**.
