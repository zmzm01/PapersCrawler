# Multi-Domain Report Enhancement

## Goal
Restructure the Markdown report from a flat list of papers to a grouped structure organized by sub-domain, with descriptions from keywords.yaml.

## Current State
- `phase_g.py` builds `paper_dict` with `matched_subdomains` (list of sub-domain keys from `llm_relevance_subfields` JSON)
- `paper_report_generator.py` renders each paper as `## Title` with per-paper sub-domain metadata line
- TOC lists papers as flat `1. Title / 2. Title / ...`

## Design

### Target Report Structure
```
# 文献报告

## 目录
- 方向一: 加速 — 激光驱动离子加速与后加速
  - Paper A
  - Paper D
- 方向二: 激光等离子体物理与诊断
  - Paper B
    (description...)
- ...

---
### 方向一: 加速 — 激光驱动离子加速与后加速

(description from keywords.yaml)

#### Paper A
...

#### Paper D
...

### 方向二: 激光等离子体物理与诊断
...

### 未分类 (papers with no sub-domain match, if any)
...
```

### Key Design Decisions
1. **Backward compatibility**: The existing flat `generate_markdown()` signature stays unchanged for callers that don't need grouping. A new mode or a new function handles sub-domain grouping.
2. **Papers can appear in multiple sections** if they match multiple sub-domains.
3. **Unclassified appendix**: Papers with empty `matched_subdomains` go in an "未分类" appendix.
4. **Sub-domain descriptions** come from `scope_definition` in keywords.yaml, passed via `phase_g.py`.
5. **TOC**: Grouped by sub-domain with paper links underneath each sub-domain.
6. **Heading levels**: Sub-domain → `##`, individual papers → `###` (adjusted from current `##`).

### Files to Change
| File | Changes |
|------|---------|
| `src/pipeline/phase_g.py` | Import `load_keywords()` or `CFG` to get `scope_definition`, pass to `generate_report()` |
| `src/processors/paper_report_generator.py` | New `generate_grouped_markdown()` + helpers; update `generate_report()` routing |
| `tests/test_report.py` | Add tests for grouped output, multi-sub-domain papers, unclassified fallback |

### Function Signatures (Draft)
```python
def generate_grouped_markdown(
    papers: List[Dict],
    scope_definition: Dict[str, Dict],
    toc: bool = False,
    results_heading_base: int = 4,
) -> str:
    """Generate Markdown report grouped by sub-domain."""

def _group_papers_by_subdomain(
    papers: List[Dict],
    scope_definition: Dict[str, Dict],
) -> dict:
    """Group papers by their matched sub-domains. Returns {subdomain_key: [papers]}."""
```

### generate_report() Change
```python
def generate_report(papers, format='markdown', toc=False, ...,
                    scope_definition=None) -> str:
    if scope_definition and fmt in ('markdown', 'md'):
        return generate_grouped_markdown(papers, scope_definition, toc=toc, ...)
    elif fmt in ('markdown', 'md'):
        return generate_markdown(papers, toc=toc, ...)
```

### No scope_definition → fallback to current flat mode (backward compatible)

## Risks
- No risk: HTML mode unchanged (no grouping)
- Low risk: test_report.py assertions on heading levels may need update if a paper now appears under `###` instead of `##` in grouped mode

## Verification
- `pytest tests/test_report.py -v` — all existing + new tests pass
- `pytest tests/ -v` — full suite passes

## Oracle Review (2026-06-15)
Accepted with these refinements:

### Q1: scope_definition parameter ✓ — pass as parameter, keep generator pure
### Q2: Heading levels — `_make_markdown_section()` gets `heading_level` param (default 2). auto-derive heading_base = heading_level + 2
### Q3: Unclassified appendix — only show when mixed (classified + unclassified both exist). Fall back to flat when ALL papers unmatched
### Q4: HTML grouping deferred — HTML path unused in production
### Q5: loading via `phase_g.py` imports `load_keywords()` ✓

### Extra Concerns
- **Duplicate papers**: Accept (low volume, correct semantics)
- **TOC anchors**: Use plain text bullets for grouped mode (existing Chinese anchor bug)
- **Test fixtures**: Add `matched_subdomains` field to sample papers
- **Phase D interaction**: Graceful degradation with INFO log

## Implementation Plan

### Files to modify (3 files):

**1. `src/processors/paper_report_generator.py`**
- New `_group_papers_by_subdomain(papers, scope_definition)` → groups + unclassified fallback
- New `generate_grouped_markdown(papers, scope_definition, toc, results_heading_base)` → sub-domain sections + TOC
- `_make_markdown_section(paper, heading_level=2, ...)` → dynamic `##`/`###` via heading_level param
- `generate_report()` → route to grouped mode when `scope_definition` provided

**2. `src/pipeline/phase_g.py`**
- `from config import load_keywords` → get `scope_definition`
- Pass to `generate_report(..., scope_definition=scope_definition)`

**3. `tests/test_report.py`**
- New test data with `matched_subdomains`
- Tests for grouping, multi-match, unclassified, unknown keys, all-unclassified fallback
