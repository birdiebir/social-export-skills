---
name: social-export-analysis
description: Analyze a large personal data export from a social platform (Facebook "Download Your Information", Instagram, Google Takeout, Twitter/X archive, etc.) — raw HTML/JSON files containing years of posts, messages, connections, activity logs. Sets up a raw/derived/analysis folder skeleton, a centralized path-config module, template-based parsing of repeating record structures, a phase-by-phase extract → join → derived-library → report pipeline, and sanity/regression checks between phases. Use when the user has a large exported personal-data archive (often tens of thousands of files, sometimes 10GB+) and wants it extracted, categorized, cross-referenced, reorganized (e.g. a browsable photo library), or scanned for a specific concern (PR risk, life-timeline, relationship analysis, account security). Trigger phrases: "分析我的 Facebook 資料匯出", "整理社交平台個資", "找出 PR 風險", "人生軌跡分析", "analyze my data export", "parse my Instagram/Facebook download".
---

# Social Export Analysis

Methodology and reusable scaffolding for turning a large, unstructured personal-data export into categorized, analyzable data — validated on a 10GB+ Facebook export (tens of thousands of message files, about 15 raw top-level categories, tens of thousands of photos). The architecture is platform-agnostic; only the **connector** (the code that parses one platform's raw file format into records) is platform-specific.

## When to use this skill

- User hands you a folder from a "download your data" export (Facebook, Instagram, Google Takeout, Twitter/X, LinkedIn, etc.) and wants it analyzed.
- The export is too large/unstructured to read directly — you need a repeatable extract pipeline, not one-off exploration.
- The goal is one or more of: chronological/topical categorization, cross-referencing between categories (joins), a browsable reorganized media library, a PR-risk / sensitive-content scan, or a narrative report.

Don't use this for small, already-structured exports (a single CSV, a small JSON file) — just read them directly.

## Core architecture (platform-agnostic)

```
<project>/
  raw/                 <- the export, untouched, exactly as extracted from the platform's zip
  derived/              <- reorganized primary content a human browses directly (e.g. a hardlinked photo library)
  analysis/
    scripts/<category>/ <- extract/join/report scripts, grouped by topic
    output/<category>/  <- their JSONL/JSON/markdown output, same category names as scripts/
    lib/
      paths.py           <- see scripts/paths_template.py — single source of truth for RAW_ROOT/DERIVED_ROOT/OUTPUT_ROOT
      connector(s)        <- platform-specific parsers (see connectors/)
      phase0_*_check.py   <- sanity/regression checks
```

Keep `scripts/<category>/` and `output/<category>/` names in sync — it's the difference between "which script produced this file" being obvious vs. a lookup. See `references/folder-layout.md` for the full rationale and a worked example.

**Never hardcode an absolute path in an extract/join/report script.** Every script imports `RAW_ROOT` / `DERIVED_ROOT` / `OUTPUT_ROOT` from `lib/paths.py` (computed from `__file__`, not a drive letter). This is what makes the whole pipeline portable across projects/machines — it's also why this skill's templates are reusable at all.

## Phase-by-phase workflow

Full detail in `references/workflow.md`. Summary:

1. **Phase 0 — reverse-engineer the format.** Open 1 sample file per category by hand. Real exports repeat a small number of record templates (e.g. Facebook HTML has exactly 3: timeline sections, field-tables, and a `_2pin` table variant). Write one parser per template, not one per file. Write a `_phase0_sanity_check.py` that runs each parser against one representative file per template and prints record counts + samples for human eyeballing before you scale up.
2. **Phase 1-3 — extract per category.** One script per topic area (identity, social, activity, security, messages, marketplace, ...), each importing the shared connector, writing JSONL to `output/<category>/data/`. Categories mirror how the user thinks about their data, not the platform's folder names.
3. **Phase 4 — joins / cross-references.** Scripts that read multiple `output/<category>/data/*.jsonl` and combine them (funnels, persona inference, topic classification). Name-matching across lists needs an explicit ambiguity policy (see workflow.md) — don't silently merge.
4. **Phase 5 — derived media library (optional).** If the export contains media (photos/videos) scattered across per-conversation/per-post folders, build a browsable reorganization using **hardlinks** (same-volume, zero extra disk, safe to re-run/idempotent) into `derived/<name>/by_person/` and `by_time/` trees + a `manifest.jsonl`. See `scripts/photo_library_template.py`.
5. **Phase 5b — chat transcripts (optional).** If you're rendering per-thread message transcripts (`derived/<kind>/<slug>/chat.html`), use `scripts/chat_html_template.py` — self/other message bubbles (sender in a project-wide `SELF_NAMES` set gets the "self" side/color, everyone else the "other" side), inline media, and a `SPECIAL_THREAD_NOTES` mechanism for edge-case threads (e.g. a thread that's actually the same human's two accounts talking to each other — see its docstring for the exact reasoning: keep normal left/right rendering, add an explanatory banner, don't collapse both sides into "self"). Append its `CHAT_BUBBLE_CSS` to `shared.css` once — don't inline a full copy per chat.html.
6. **Phase 6 — reports.** Synthesize everything in `output/` into a handful of human-readable markdown reports, one per concern area, not one giant dump.
7. **Regression checks between phases.** Any time you touch a parser after Phase 1 output already exists, re-run it against the same source files and diff counts against the existing JSONL (`phase0_regression_check.py` pattern) — silent parser drift is the main risk in this kind of work.

## Connectors (platform-specific)

`scripts/connectors/facebook_html/fb_common.py` is the reference implementation for Facebook's "Download Your Information" HTML export — 3 record templates covering the vast majority of Facebook's ~50 export file types (see its docstring). Copy it into a new project's `analysis/lib/` when the source is a Facebook HTML export.

For a different platform/format (Instagram or Google Takeout JSON, Twitter/X archive, LinkedIn export, ...):
1. Sample a few files, identify the repeating record shape(s) (usually 1-3 for JSON-based exports, often even simpler than HTML).
2. Write a small connector module with the same shape as `fb_common.py`: one `parse_<template>(path, category) -> (records, ...)` function per template, all returning plain dicts with at least `category`, `source_file`, `timestamp`.
3. Everything downstream (extract scripts, joins, reports, phase0 checks) is connector-agnostic as long as records have that shape.

## Setting up a new project

1. Create the `raw/derived/analysis/{scripts,output,lib}` skeleton (`references/folder-layout.md`).
2. Copy `scripts/paths_template.py` → `<project>/analysis/lib/paths.py`, adjust `parents[N]` if your lib depth differs from `analysis/lib/`.
3. Copy the relevant connector into `analysis/lib/` (or write a new one per above).
4. Copy `scripts/phase0_checks_template.py` as a starting point for the Phase 0 sanity check; sample 1 file per template family.
5. Write extract scripts per category, following the pattern in `references/workflow.md`.
6. If the export has media, adapt `scripts/photo_library_template.py`.
6a. Adapt `scripts/coverage_check_template.py` so every raw file must end up somewhere. It checks message pages against the extractor's actual read list and decides "referenced" by sha256 (`--self-test` shows both rules on made-up data).
7. Create `private/` (gitignored) for the user's own personal data, such as mask-exemption lists, and commit a `private.example/` template. Code reads only a path from config. See `references/privacy.md`.
8. If the user has more than one account, read `references/multi-account.md` and write the account, sender and period rules into the project's decision log before the first analysis.

## Known pitfalls (from the Facebook project this was extracted from)

- **Encoding**: Windows terminals often default to a codepage (cp950/cp1252) that can't print CJK/emoji — set `PYTHONIOENCODING=utf-8` when running scripts interactively, don't "fix" it by stripping characters from the data.
- **Message/media volume**: a single export can have tens of thousands of small files (e.g. tens of thousands of `message_N.html` files, 10GB+). Stream — never load a whole category into memory or write one giant JSONL of raw text; aggregate into counters/small indices as you go (see `references/workflow.md` § streaming aggregation).
- **Name-matching across lists (joins)**: a person's display name isn't a stable key over many years (renames, duplicates). Only treat a match as confident when the name is unique in *both* lists being joined; everything else goes to an explicit `ambiguous` bucket with the policy documented in the output's `_meta.caveats`, never silently merged.
- **NTFS hardlinks for derived media libraries**: `os.link()` is same-volume only, is idempotent to re-run (check `stat().st_ino` before linking), and moving/renaming either side afterward does not break the link — but any manifest that records "original path relative to X" goes stale if X moves. Treat that as a known cosmetic limitation, not a bug to chase.
- **PII/sensitive-content scans**: keyword/regex prefilters (see the PR-risk pattern in `references/workflow.md`) will always need a human review pass — ship them as a shortlist + a stratified random sample of what they *didn't* flag, not as a final verdict.
- **Media `src` paths in chat transcripts are relative to the export root, not the thread folder**: Facebook's raw `<img src="...">` (and video/audio) attributes are written relative to the whole export root (e.g. `your_facebook_activity/messages/<category>/<thread_id>/photos/x.jpg`), even from an HTML file that already lives deep inside that same thread folder. A hardlinked derived chat.html sits next to a bare `photos/` folder, not a full export tree, so writing that path straight into `<img src>` 404s. Always resolve `(RAW_ROOT / media_path)` to an absolute path first, then `os.path.relpath()` it against the thread's own folder — see `scripts/chat_html_template.py`'s `render_msg_body()`.

## Lessons from later iterations (2026-10; details in references)

The pitfalls above come from the first build. A later rebuild turned up more: one codebase, two exports of the same person, many batches with parallel agents. Read the matching reference before each stage:

| When | Read | The one thing most likely to bite |
|---|---|---|
| Writing or changing a parser | `references/pitfalls.md` § A | Meta truncates message file names (down to just `.html`) when paths are long, and a strict regex silently skips whole threads. A text field that holds only an IP address is the user's own sticker or photo, not a system notice. |
| Trusting a coverage, regression or quote PASS | `references/pitfalls.md` § B | Coverage judged by inference ("deep enough = read") passes on missing data, so check against the extractor's actual read list. Duplicate media must be matched by sha256, not path. A mechanical PASS doesn't mean the narrative is correct. |
| The user has two or more accounts | `references/multi-account.md` | Account = which export + sender alias. Period = date. The old account keeps sending after the switch (sales, lent out, compromised). Shared threads appear in both exports: count them once and analyze them once. |
| Rendering pages with personal data, writing tests, handling tmp files | `references/privacy.md` | Mask before truncating. The user's own exemptions go in `private/`. Test fixtures never use real data. Delete reading dumps when done. |
| Several agents working at once, or wrap-up and packaging | `references/parallel-agents.md` | Agents write only in their own scope. The main line alone runs package, check, progress and commit. Review the staged list before committing. Send reports to a file. Verify PM numbers against L1. Keep the machine awake during packaging. |
| Planning a fix that changes counts, writing back user answers, or deleting old copies (added 2026-10-01) | `references/pitfalls.md` § C | Run a read-only trial before deciding: an estimate of dozens turned out to be tens of thousands, so add a flag instead of redefining a count. Write-back scripts dry-run by default, and "0 changes" is a red flag. Delete only after backup → 100% read-back → full SHA-256 subset check → user approval. |
| Building yearly stats or interest timelines, comparing mirrored threads, or running packaging (added 2026-10) | `references/pitfalls.md` § D | A deactivated account is labelled differently in each export. Some timestamps are re-stamped by Meta, so use the original action records. AI chats also live in the inbox, so share one `is_ai_thread()`. Run packaging alone, because parallel heavy jobs get it killed. |
| Notes might contain phone numbers, emails or addresses (added 2026-10) | `references/privacy.md` (PII scan section) + `scripts/pii_scan_template.py` | Scan the notes themselves and wire it into verify (WARN first, then FAIL). Inside quotes, mask with "…" so strict verification still passes. Keep rules need a written reason. |
| More than ~10 agents, or a separate PM session (added 2026-10) | `references/parallel-agents.md` (scaling, PM session sections) | Exclusive scopes + two phases + one committer. Pair every narrative agent with a semantic reviewer. Cross-session messages may wait for user approval. Verify any "the user said" in an agent report. |
| Reading many small threads in full, counting typed messages, or matching notes folders to thread IDs (added 2026-10) | `references/pitfalls.md` § E | Call records are timestamped at the end of the call. Blank content is usually an export gap, so check raw HTML once and don't guess. Reaction-only sections can be counted as typed text. Don't split folder names on the first `__`, and don't trust `glob` with `[ ]` in names. |
| Working on an Instagram export, or writing dates into a report from any export (added 2026-10) | `references/pitfalls.md` § F | Instagram HTML times are a fixed UTC-8. Converting the parsed records isn't enough: hand-copied single dates in the report stay a day off. Threads files share names with Instagram ones. One export can't show who unfollowed you, so diff two exports. |
| Splitting a fact check across agents, packaging while other sessions run, or logging time and usage (added 2026-10) | `references/parallel-agents.md` (long-tail section) | Give every cross-side cluster one merge owner and assert one row per cluster. Check other sessions are idle before packaging. Use timestamps, not self-reported durations; usage numbers are machine-wide. |
| Closing a project: writing checked facts back to the knowledge base, asking the user final questions, handing off (added 2026-10) | `references/parallel-agents.md` (closing section) | Split writers by file zone and let each checklist row's destination decide the owner. Ask open questions once, ranked, at the end. Check that the AI-written notes are inside backup and sync before closing. |
| A step is blocked by the auto-mode permission classifier, or a fix needs re-extraction while others read `data/` (added 2026-10-01) | `references/parallel-agents.md` (classifier and two-phase sections) | Don't work around it. Get the user's own words, then the main line runs the step itself, or a new agent gets the quote in its initial prompt. Phase 1 changes code, tests and does a read-only trial; phase 2 re-extracts after the readers finish. |

How to keep this growing: each project keeps its own concrete `經驗與避雷.md` (module names and decision IDs are fine there). When a lesson repeats, or would make a conclusion wrong, distill a de-identified version into these references with fictional examples, and add a row here if it changes what to read first.
