# -*- coding: utf-8 -*-
"""
Template: raw-file coverage check — every file in the raw export must end up
somewhere (a parsed record, a referenced media file, a fallback page, or an
exclusion entry with a reason). Anything else is "unassigned" and fails.

Two rules here come from real misses (references/pitfalls.md § B1, B2):

1. Judge "was this message HTML read?" against the extractor's ACTUAL read list,
   not by inference. The old rule "any HTML deep enough under messages/ counts as
   read" marked truncated page names (message.html, mes.html, .html ...) as read
   although no parser had touched them; coverage and regression both said PASS
   while whole threads were missing. Have the messages extractor write the list
   of files it parsed (e.g. manifest extra.message_files, from
   fb_common.find_message_files) and compare against that. If an old manifest has
   no list, fall back to the old rule and print a warning.

2. Decide "is this raw file referenced?" by content (sha256), not path. A media
   store that keeps one copy per sha256 records only one path per hash, so every
   other path with the same bytes looks unreferenced and the orphan page fills up
   with files that are already shown elsewhere. A hash that really is
   unreferenced is listed once (first path in sort order).

Copy to <project>/analysis/scripts/<checks>/check_coverage.py and wire the ADAPT
parts to your project's manifests. Standard library only.
Run `python coverage_check_template.py --self-test` for a self-test on made-up data.
"""
import hashlib
import json
import sys
from pathlib import Path

# ---- ADAPT: export-relative roots ----
MSG_ROOT = "your_facebook_activity/messages/"   # <MSG_ROOT><category>/<thread>/<page>.html
THREAD_LEVEL_DEPTH = 3                           # slashes in "…/messages/<category>/<thread>/<file>"
ATTACHMENT_DEPTH = 5                             # deeper html inside a thread folder = attachment (files/*.html)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def build_raw_manifest(raw_root):
    """{export-relative posix path: sha256} for every file under raw_root.
    Cache this to a file (e.g. _manifest.sha256) on big exports; hashing 10GB+ takes a while."""
    raw_root = Path(raw_root)
    return {p.relative_to(raw_root).as_posix(): sha256_file(p)
            for p in sorted(raw_root.rglob("*")) if p.is_file()}


def classify_message_html(rel, read_list):
    """Classify an HTML file under MSG_ROOT.

    'read'        thread-level page that the extractor actually parsed
    'attachment'  HTML nested deeper in a thread folder (needs a media reference to count)
    'unread'      thread-level page the extractor never parsed -> FAIL
    None          not under MSG_ROOT at thread level

    read_list=None means the manifest predates read lists: old inference rule, with a warning."""
    if not (rel.startswith(MSG_ROOT) and rel.count("/") >= THREAD_LEVEL_DEPTH):
        return None
    if read_list is None or rel in read_list:
        return "read"
    return "attachment" if rel.count("/") >= ATTACHMENT_DEPTH else "unread"


def select_orphans(rel2sha, referenced_raw, is_excluded):
    """Raw files that need an orphan/fallback page, in path order: not HTML, not
    excluded, and whose CONTENT (sha256) no page references. Same-content
    unreferenced files are listed once (first path). A referenced path missing
    from rel2sha falls back to path comparison."""
    ref_shas = {rel2sha[r] for r in referenced_raw if r in rel2sha}
    picked, seen = [], set(ref_shas)
    for rel in sorted(rel2sha):
        if rel.lower().endswith(".html") or rel in referenced_raw or is_excluded(rel):
            continue
        h = rel2sha[rel]
        if h in seen:
            continue
        seen.add(h)
        picked.append(rel)
    return picked


def check(rel2sha, consumed_html, read_list, referenced_raw, fallback_pages, excluded_reason):
    """Assign every raw file a destination. Returns (rows, unassigned).

    rel2sha          {rel: sha256} for the whole raw export
    consumed_html    {rel: domain} HTML files a non-message extractor parsed (from its manifest's sources)
    read_list        set of message pages the messages extractor parsed, or None for old manifests
    referenced_raw   set of raw paths some output page / transcript references as media
    fallback_pages   {rel: page} HTML converted by a generic fallback converter
    excluded_reason  callable rel -> reason string or None (exclusion list with reasons)"""
    if read_list is None:
        print("[WARN] messages manifest has no read list; using the old 'deep enough = read' rule. "
              "Re-run the messages extractor so truncated page names are actually checked.")
    ref_shas = {rel2sha[r] for r in referenced_raw if r in rel2sha}
    rows, unassigned = [], []
    for rel in sorted(rel2sha):
        is_html = rel.lower().endswith(".html")
        msg_kind = classify_message_html(rel, read_list) if is_html else None
        reason = excluded_reason(rel)
        if reason:
            kind, where = "excluded", reason
        elif is_html and rel in consumed_html:
            kind, where = "extractor", consumed_html[rel]
        elif msg_kind == "read":
            kind, where = "extractor", "messages"
        elif is_html and rel in fallback_pages:
            kind, where = "fallback_page", fallback_pages[rel]
        elif (not is_html or msg_kind == "attachment") and (rel in referenced_raw or rel2sha[rel] in ref_shas):
            kind, where = "media_ref", "" if rel in referenced_raw else "(same content as a referenced file)"
        else:
            kind, where = "unassigned", ""
            unassigned.append(rel)
        rows.append((rel, kind, where))
    return rows, unassigned


def main():
    # ADAPT: load these from your project's manifests, then write rows to a CSV.
    print("ADAPT main(): load rel2sha / consumed_html / read_list / referenced_raw / fallback_pages, "
          "call check(), write the rows to a CSV and exit 1 if anything is unassigned.")
    sys.exit(2)


# ------------------------------------------------------- self-test --

def _self_test():
    import tempfile
    t = "your_facebook_activity/messages/inbox/"
    read_list = {t + "persona_1/message_1.html"}
    # read list: a truncated page that was never parsed must FAIL, not pass by depth
    assert classify_message_html(t + "persona_1/message_1.html", read_list) == "read"
    assert classify_message_html(t + "personb_2/mes.html", read_list) == "unread"
    assert classify_message_html(t + "persona_1/files/doc.html", read_list) == "attachment"
    assert classify_message_html("your_facebook_activity/posts/your_posts_1.html", read_list) is None
    assert classify_message_html(t + "personb_2/mes.html", None) == "read"          # old rule, warned

    # sha256: same content as a referenced file is not an orphan; duplicates listed once
    none = lambda _r: False
    assert select_orphans({"a/1.jpg": "h1", "b/1_copy.jpg": "h1", "c/2.jpg": "h2"}, {"a/1.jpg"}, none) == ["c/2.jpg"]
    assert select_orphans({"z/dup.jpg": "h3", "y/dup.jpg": "h3", "x/solo.mp4": "h4"}, set(), none) == ["x/solo.mp4", "y/dup.jpg"]
    assert select_orphans({"p/page.html": "h5", "p/ok.png": "h7", "p/ok_dup.png": "h7"}, set(), none) == ["p/ok.png"]
    assert select_orphans({"a/keep.jpg": "h8", "b/drop.jpg": "h8"}, set(), lambda r: r.startswith("b/")) == ["a/keep.jpg"]
    assert select_orphans({"a/1.jpg": "h1"}, {"zz/unknown.jpg", "a/1.jpg"}, none) == []

    # full check on a tiny fake export
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        files = {
            t + "persona_1/message_1.html": b"<html>a</html>",
            t + "personb_2/mes.html": b"<html>b</html>",               # truncated, never parsed
            t + "persona_1/photos/p.jpg": b"JPEG-1",
            t + "personb_2/photos/p_copy.jpg": b"JPEG-1",              # same bytes, other path
            "your_facebook_activity/posts/your_posts_1.html": b"<html>c</html>",
            "ads_information/odd_page.html": b"<html>d</html>",
        }
        for rel, data in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(data)
        rel2sha = build_raw_manifest(root)
        assert rel2sha[t + "persona_1/photos/p.jpg"] == hashlib.sha256(b"JPEG-1").hexdigest()
        rows, unassigned = check(
            rel2sha,
            consumed_html={"your_facebook_activity/posts/your_posts_1.html": "activity"},
            read_list=read_list,
            referenced_raw={t + "persona_1/photos/p.jpg"},
            fallback_pages={"ads_information/odd_page.html": "other/ads_information/odd_page.html"},
            excluded_reason=lambda r: None,
        )
        kinds = {rel: kind for rel, kind, _ in rows}
        assert unassigned == [t + "personb_2/mes.html"], unassigned
        assert kinds[t + "personb_2/photos/p_copy.jpg"] == "media_ref", kinds
        assert kinds[t + "persona_1/message_1.html"] == "extractor"
    print("coverage_check self-test: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        main()
