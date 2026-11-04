# Workflow

Phase-by-phase methodology, validated on a Facebook export (about 15 raw top-level categories, 10GB+ of messages across tens of thousands of files, tens of thousands of photos).

## Phase 0 — reverse-engineer the format before writing any extract script

Large exports repeat a small, finite number of record templates across many files — you're looking for the templates, not writing per-file parsers.

1. Open one sample file per suspected category by hand (or `grep`/search for a recognizable repeating marker — a CSS class, a JSON key, a delimiter).
2. Identify the repeating chunk boundary (e.g. Facebook HTML: `<section class="_a6-g" aria-labelledby="`) and the fields inside each chunk.
3. Write one parser function per template family, not per file. On the Facebook project, ~50 distinct exported HTML files reduced to 3 template families:
   - **timeline**: header + optional free-text content + optional footer timestamp/URL.
   - **field-table**: repeating label/value `<tr>` rows inside a marked section.
   - **`_2pin` table variant**: same section-splitting as timeline, but content is a table with a different class prefix.
   Two more one-off patterns existed for specific files (nested-value extraction, alternating-row pairing) — expect a couple of true one-offs even after templates are identified; don't force them into an existing template function.
4. Write `phase0_sanity_check.py`: for each template, parse one representative file and print `len(records)` + 2-3 samples. A human (or you) eyeballs this before scaling to all files of that template — catches a wrong regex before it silently produces 0 or garbage records across dozens of files.
5. Once Phase 1+ output exists, any time a parser changes, write/run a `phase0_regression_check.py`: re-parse the same source files and diff record counts against the already-written JSONL. This is the main defense against silent parser drift when you go back to fix an edge case.

## Phase 1-3 — extract per category

- One script per topic area the *user* cares about (identity, social connections, activity, security events, messages, marketplace, ...) — not one script per raw export file. A single script commonly reads 2-4 related raw files and writes 2-4 related JSONL outputs.
- Every record gets at minimum: `category`, `source_file`, `timestamp` (empty string if the source has none — don't invent one).
- Each script's own docstring should document expected record counts (`~N 筆`) from the first successful run — makes regression checks and future re-runs self-verifying at a glance.
- **Streaming for high-volume categories.** If a category has thousands+ of source files (messages, in this case tens of thousands of files / 10GB+), never accumulate raw text in memory or write it back out as one giant JSONL. Stream file-by-file, message-by-message, updating small counters/indices (hourly histogram, per-thread counts, emoji frequency, per-thread first/last timestamp) and discard the text immediately after. Only persist the small aggregates.

## Phase 4 — joins / cross-references

Combine multiple `output/<category>/data/*.jsonl` files into derived insights (funnels, persona inference from price/behavior data, topic classification from keyword rules, domain distribution from URLs).

**Name-matching policy** (the recurring hard part): when joining two lists by a person's display name (e.g. "who later became a friend" from an imported-contacts list vs. a friends list), a name string is not a stable unique key over a multi-year export — people get renamed, duplicate entries exist, common names collide.

- Only count a match as `confident` when the name is unique in *both* lists being joined.
- Everything else — name appears >1 time in either list, or matches ambiguously — goes into a separate `ambiguous` bucket, never silently merged into the confident count.
- Document the caveat in the output JSON itself (a `_meta.caveats` field), not just in a comment — anyone consuming the output later (including a future report-writing pass) needs to see it without re-reading the join script.
- Keyword-rule classification (e.g. topic-tagging pages/groups/interests by substring match) always leaves an "unclassified" bucket — write it out as its own review file (with keyword-extraction like jieba/RAKE to suggest rule additions) rather than forcing a low-confidence guess into a real category.

## Phase 5 — derived media library (if the export has media)

Goal: a browsable reorganization of scattered media files (e.g. photos nested inside thousands of per-conversation folders) without duplicating any data.

- Use hardlinks (`os.link()`), not copies — same-volume only, zero extra disk regardless of total size.
- Build at least two parallel views: by-person/by-category, and by-time (year/month) — different browsing needs.
- Idempotency: before creating a link, check `dst.stat().st_ino == src.stat().st_ino` — makes the whole builder safe to re-run after adding new source files, without re-linking or erroring on existing ones.
- Timestamp resolution: prefer parsing an actual timestamp from an accompanying export file (e.g. the HTML page that references the photo); fall back to file mtime, and mark that record's `confidence` field accordingly (`html` vs `fallback-mtime`) so low-confidence entries can be spot-checked later — route them into a separate `unknown/` bucket alongside the confident ones.
- Emit a `manifest.jsonl` (one record per media file: new paths in each view, original path, confidence, sender/context) — this is what later scripts (e.g. a report referencing "photos from person X") join against, and what a human uses to audit fallback entries.
- Caveat to document, not fix: if `raw/` ever moves after the library is built, any "original path" field recorded relative to the old root goes stale as *metadata* — the hardlinks themselves stay valid regardless (an inode doesn't care what directory entries point to it). Don't chase rebuilding the manifest for this; note the limitation.

## Phase 6 — reports

- **Raw-data browsing list, before any analysis exists**: for any domain with many individually-sized records (conversations, groups, posts, comment threads), build a simple sortable/searchable archive list — one card/row per record, sorted descending by size (message count, word count, comment count — whatever "length" means for that domain), with a text filter box and a link out to the full raw content. This is the default, zero-analysis deliverable for a domain: the user should be able to see *what exists and how big it is* before deciding whether any analysis is worth doing on it. Already validated at scale (a few thousand conversations, sorted by message count, filterable) as `messages/report.html` — copy that shape for other domains (posts, comment threads) rather than reinventing a layout each time. Downstream skills (e.g. `social-export-insights`'s "輕/中/深" tiers) build on top of this list; they should never be the reason this list gets built — build it first, unconditionally, then let analysis be a separate, opt-in decision per record.
- Synthesize `output/` into a handful of markdown reports split by *concern*, not one giant dump — e.g. separate "life timeline", "relationship network", "fun stats", "practical/PR" reports rather than one 2000-line file.
- Each report-building function loads only the JSONL/JSON it needs via a small `load_jsonl(rel_path)` / `load_json(rel_path)` helper relative to `OUTPUT_ROOT` — keeps report scripts trivially re-runnable after any upstream extract/join re-runs.
- For a sensitive-content / PR-risk scan specifically: keyword/regex prefilter → shortlist candidates + a **stratified random sample of what wasn't flagged** (to catch what keywords miss, e.g. sarcasm/coded language) → human or LLM review pass → final severity-grouped report. Never treat the keyword-filtered shortlist alone as the final answer.
