# -*- coding: utf-8 -*-
"""
Reference connector: Facebook "Download Your Information" HTML export.

Copy into <project>/analysis/lib/fb_common.py when the source export is
Facebook's HTML format. Extracted from a project that used this to parse
~50 distinct exported HTML file types down to 3 repeating record templates
(plus two true one-offs) — see references/workflow.md § Phase 0 in this
skill for the general method this was derived from.

Known templates:
  1. timeline: <section class="_a6-g" aria-labelledby="..."><h2 ...>HEADER</h2>
     [<div class="_2ph_ _a6-p">CONTENT</div></div>]
     [<footer ...>[<a href="URL">]<div class="_a72d">TS</div>[</a>]</footer>]</section>
  2. field-table: repeating <tr><td class="_a6_q">LABEL</td><td class="_2piu _a6_r">VALUE</td></tr>
     rows, usually nested inside a <table> starting at FIELD_TABLE_MARK, with an
     outer <footer><div class="_a72d">TS</div></footer>
  3. _2pin table variant (notifications.html, security_and_login_information/*.html):
     records are still split the same way as timeline (<section class="_a6-g"
     aria-labelledby="...">HEADER</h2>), but content is a <table> instead of free
     text, with fields under _2pin-prefixed classes:
       simple row: <td class="_2pin _a6_q">LABEL</td><td class="_2pin _2piu _a6_r">VALUE</td>
       colspan row: <td colspan="2" class="_2pin _a6_q">LABEL<div>[<div>]VALUE[</div>]</div></td>

Two more one-off patterns are included for specific known files: a nested-value
extractor (name/cookie-hash values buried in a nested <section> instead of a
sibling <td>) and an alternating-row pairer (a file with no <section> splitting
at all, just two <tr> rows per record). Expect a couple of true one-offs even
after you've found the main templates in a new export — don't force them into
one of the template functions above.

Timestamps are parsed from Facebook's Traditional-Chinese locale format
("8 月 15, 2017 9:28:01 下午"); adjust TS_RE for other locales/platforms.

Fixes ported from a later rebuild (2026-10-01; background in
references/pitfalls.md):
  - find_message_files() / message_page(): also accepts message page names that
    Meta truncated because the path was too long (A1).
  - iter_messages(): splits sender-less sections out of the previous message
    as type="system" records instead of merging them (A6); optional stats dict.
  - iter_jsonl(): reads JSONL line by line, safe for U+2028 in message text (A9).
  - classify_and_clean(): stickers (stickers_used/) and document attachments
    (.../files/) no longer collapse into empty text messages.
  - classify_group_event(): group names get their own 100-char cap, so long
    rename events are not dropped by the 20-char person-name cap.
  - split_participants(): splits the last 「和」 only when provable.
Run `python fb_common.py` for a self-test on made-up HTML fragments.
"""
import re
import html
import json
from datetime import datetime

# ---------------------------------------------------------------- base utils --

TAG_RE = re.compile(r'<[^>]+>')
BR_RE = re.compile(r'<br\s*/?>', re.I)


def strip_tags(s):
    if s is None:
        return ""
    s = BR_RE.sub("\n", s)
    s = TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


TS_RE = re.compile(
    r'(\d{1,2})\s*月\s*(\d{1,2}),\s*(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(上午|下午)'
)


def parse_ts(raw):
    """Parse a zh-Hant Facebook timestamp string into datetime, None on failure."""
    m = TS_RE.search(raw or "")
    if not m:
        return None
    month, day, year, hour, minute, second, ampm = m.groups()
    month, day, year = int(month), int(day), int(year)
    hour, minute, second = int(hour), int(minute), int(second)
    if ampm == "上午":
        if hour == 12:
            hour = 0
    else:
        if hour != 12:
            hour += 12
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def extract_all_timestamps(text):
    """Find every zh-Hant timestamp string in a block of text, return a list of
    datetimes (used for e.g. browser_cookies.html where one cookie maps to a
    list of session dates)."""
    out = []
    for m in TS_RE.finditer(text or ""):
        dt = parse_ts(m.group(0))
        if dt:
            out.append(dt)
    return out


def read_text(path):
    return path.read_text(encoding="utf-8")


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for seq, rec in enumerate(records, start=1):
            f.write(json.dumps({"seq": seq, **rec}, ensure_ascii=False) + "\n")


def iter_jsonl(path):
    """Yield one record per JSONL line.

    Iterates the file object instead of calling str.splitlines(): message text
    can contain U+2028 / U+2029 (and json.dumps(ensure_ascii=False) writes them
    raw), and splitlines() treats those as line breaks, cutting one record into
    two broken halves. Iterating a text-mode file splits on newline characters
    only (\\n, \\r\\n, \\r), never on U+2028."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# --------------------------------------------------------- timeline template --

A6G_SPLIT_RE = re.compile(r'<section class="_a6-g" aria-labelledby="')

TIMELINE_HEADER_RE = re.compile(
    r'^[^"]*"><h2[^>]*>(?P<header>.*?)</h2>'
    r'(?:<div class="_2ph_ _a6-p">(?P<content>.*?)</div></div>)?'
    r'(?:<footer[^>]*>(?:<a[^>]*href="(?P<url>[^"]*)"[^>]*>)?'
    r'<div class="_a72d">(?P<ts>[^<]*)</div>)?',
    re.S,
)


def parse_timeline(path, category):
    """Return (records, bad, total_chunks). Each record:
    {category, source_file, header, text, timestamp, url}."""
    raw = read_text(path)
    chunks = A6G_SPLIT_RE.split(raw)[1:]
    out, bad = [], 0
    for chunk in chunks:
        m = TIMELINE_HEADER_RE.match(chunk)
        if not m:
            bad += 1
            continue
        out.append({
            "category": category,
            "source_file": path.name,
            "header": strip_tags(html.unescape(m.group("header"))),
            "text": strip_tags(m.group("content")) if m.group("content") else "",
            "timestamp": (m.group("ts") or "").strip(),
            "url": m.group("url") or "",
        })
    return out, bad, len(chunks)


# -------------------------------------------------------- field-table template --

FIELD_TABLE_MARK = (
    '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">'
    '<section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p"><table'
)
ROW_RE = re.compile(
    r'<tr><td class="_a6_q">(?P<label>.*?)</td><td class="_2piu _a6_r">(?P<value>.*?)</td></tr>',
    re.S,
)
TS_TAIL_RE = re.compile(r'<div class="_a72d">(?P<ts>[^<]*)</div>')


def split_on_literal_marker(raw, marker):
    """Split on a literal marker string (more general than FIELD_TABLE_MARK,
    lets nested field-tables use an inner-only-unique marker as the split
    point so the outer FIELD_TABLE_MARK doesn't split too early)."""
    parts = raw.split(marker)[1:]
    return parts


def parse_field_tables(path, category, split_marker=FIELD_TABLE_MARK, row_re=ROW_RE):
    """Return (records, total_parts). Each record:
    {category, source_file, fields, timestamp}."""
    raw = read_text(path)
    parts = split_on_literal_marker(raw, split_marker)
    out = []
    for part in parts:
        end = part.find(split_marker)
        chunk = part if end == -1 else part[:end]
        fields = {}
        for m in row_re.finditer(chunk):
            label = strip_tags(m.group("label"))
            value = strip_tags(m.group("value"))
            fields.setdefault(label, []).append(value)
        fields_flat = {k: (v[0] if len(v) == 1 else v) for k, v in fields.items()}
        ts_m = TS_TAIL_RE.search(chunk)
        out.append({
            "category": category,
            "source_file": path.name,
            "fields": fields_flat,
            "timestamp": (ts_m.group("ts").strip() if ts_m else ""),
        })
    return out, len(parts)


# ------------------------------------------------- _2pin table variant (template 3) --

ROW_2PIN_SIMPLE_RE = re.compile(
    r'<td class="_2pin _a6_q">(?P<label>.*?)</td>'
    r'<td class="_2pin _2piu _a6_r">(?P<value>.*?)</td>',
    re.S,
)
ROW_2PIN_COLSPAN_RE = re.compile(
    r'<td colspan="2" class="_2pin _a6_q">(?P<label>[^<]*)<div>(?P<value>.*?)</div></td>',
    re.S,
)


def parse_2pin_sections(path, category):
    """For notifications.html, security_and_login_information/*.html: split
    the same way as timeline, fields use _2pin-prefixed table cell classes.
    Return (records, total_chunks). Each record:
    {category, source_file, header, fields, timestamp}.
    Timestamp prefers the fields' "時間" key (these files usually lack a
    footer/_a72d)."""
    raw = read_text(path)
    chunks = A6G_SPLIT_RE.split(raw)[1:]
    out = []
    for chunk in chunks:
        header_m = re.match(r'^[^"]*"><h2[^>]*>(?P<header>.*?)</h2>', chunk, re.S)
        header = strip_tags(html.unescape(header_m.group("header"))) if header_m else ""
        fields = {}
        for m in ROW_2PIN_SIMPLE_RE.finditer(chunk):
            fields[strip_tags(m.group("label"))] = strip_tags(m.group("value"))
        for m in ROW_2PIN_COLSPAN_RE.finditer(chunk):
            fields[strip_tags(m.group("label"))] = strip_tags(m.group("value"))
        ts_m = TS_TAIL_RE.search(chunk)
        timestamp = (ts_m.group("ts").strip() if ts_m else fields.get("時間", ""))
        out.append({
            "category": category,
            "source_file": path.name,
            "header": header,
            "fields": fields,
            "timestamp": timestamp,
        })
    return out, len(chunks)


# ------------------------------------------------------- nested-value extraction (one-off) --

def extract_nested_value(chunk, label="名稱"):
    """For templates where a value is buried in a nested <section> instead of
    a sibling <td> (names, cookie hashes):
      <div class="_2ph_ _a6_q">LABEL</div><div><div>
        <section class="_3-95 _a6-g"><div class="_2pi8 _2pic _a6-p">VALUE</div></section>
    Return string, or None if not found."""
    pat = re.compile(
        r'<div class="_2ph_ _a6_q">' + re.escape(label) + r'</div>'
        r'<div><div><section class="_3-95 _a6-g">'
        r'<div class="_2pi8 _2pic _a6-p">(?P<value>.*?)</div></section>',
        re.S,
    )
    m = pat.search(chunk)
    return strip_tags(m.group("value")) if m else None


def extract_nested_name(chunk):
    """Shorthand for extract_nested_value(chunk, "名稱")."""
    return extract_nested_value(chunk, "名稱")


def parse_field_table_with_nested_name(path, category, row_re=ROW_RE):
    """Outer shape is a standard field-table (split on FIELD_TABLE_MARK), but
    the name field is buried in a nested section (see extract_nested_name) and
    can't be captured by row_re. Return (records, total_parts). Each record:
    {category, source_file, name, fields, timestamp}."""
    raw = read_text(path)
    parts = split_on_literal_marker(raw, FIELD_TABLE_MARK)
    out = []
    for part in parts:
        end = part.find(FIELD_TABLE_MARK)
        chunk = part if end == -1 else part[:end]
        fields = {}
        for m in row_re.finditer(chunk):
            label = strip_tags(m.group("label"))
            value = strip_tags(m.group("value"))
            fields.setdefault(label, []).append(value)
        fields_flat = {k: (v[0] if len(v) == 1 else v) for k, v in fields.items()}
        ts_m = TS_TAIL_RE.search(chunk)
        out.append({
            "category": category,
            "source_file": path.name,
            "name": extract_nested_name(chunk),
            "fields": fields_flat,
            "timestamp": (ts_m.group("ts").strip() if ts_m else ""),
        })
    return out, len(parts)


# ------------------------------------------------------- alternating-row pairing (one-off) --

def pair_alternating_rows(path, category, key_label, value_label):
    """For files with no <section> splitting at all, just one big table where
    each record is two consecutive <tr> rows (key_label row followed by
    value_label row). Return (records, total_rows). Each record:
    {category, source_file, name, timestamp}."""
    raw = read_text(path)
    rows = [(strip_tags(m.group("label")), strip_tags(m.group("value")))
            for m in ROW_RE.finditer(raw)]
    out = []
    i = 0
    while i + 1 < len(rows):
        (l1, v1), (l2, v2) = rows[i], rows[i + 1]
        if l1 == key_label and l2 == value_label:
            out.append({
                "category": category,
                "source_file": path.name,
                "name": v1,
                "timestamp": v2,
            })
            i += 2
        else:
            i += 1
    return out, len(rows)


# ------------------------------------------------------- streaming message parsing --

SECTION_SPLIT_RE = A6G_SPLIT_RE
HEADER_RE = re.compile(
    r'^[^"]*"><h2 class="_2ph_ _a6-h _a6-i" id="[^"]*">(?P<sender>.*?)</h2>'
    r'<div class="_2ph_ _a6-p">(?P<content>.*)</div><footer class="_3-94 _a6-o">'
    r'<div class="_a72d">(?P<ts>[^<]*)</div></footer>',
    re.S,
)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)
# A section with no aria-labelledby (and no <h2> sender) is NOT a split point for
# SECTION_SPLIT_RE, so it ends up inside the previous message's content (HEADER_RE's
# content group is greedy and runs to the last footer). Split it back out on
# "footer close + next unlabelled section open"; the capture group is each piece's
# own timestamp (the last piece's timestamp is HEADER_RE's ts).
EMBEDDED_SECTION_RE = re.compile(
    r'</div><footer class="_3-94 _a6-o"><div class="_a72d">([^<]*)</div></footer></section>'
    r'<section class="_a6-g">')
CONTENT_DIV_OPEN = '<div class="_2ph_ _a6-p">'
SYSTEM_TYPE = "system"

VIDEO_SRC_RE = re.compile(r'<video[^>]*\bsrc="([^"]+)"')
IMG_SRC_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"')
AUDIO_SRC_RE = re.compile(r'<audio[^>]*\bsrc="([^"]+)"|<source[^>]*\bsrc="([^"]+\.mp4)"')
# Anchor on the export's own relative prefix, so a shared external link whose URL
# happens to contain "/files/" (e.g. a course site) is not mistaken for an attachment.
FILE_HREF_RE = re.compile(r'<a[^>]*\bhref="(your_facebook_activity/messages/[^"]+/files/[^"]+)"')


def classify_and_clean(content_html):
    """Return (msg_type, text, media_path).

    Types: unsent / media (video) / photo / gif (GIFs AND stickers) / audio /
    file (document attachment) / link / text."""
    if "這則訊息已收回" in content_html:
        return "unsent", "", None

    m = VIDEO_SRC_RE.search(content_html)
    if m:
        return "media", strip_tags(content_html), m.group(1)

    m = IMG_SRC_RE.search(content_html)
    if m and ("/photos/" in m.group(1) or "/gifs/" in m.group(1) or "/stickers_used/" in m.group(1)):
        # Stickers live under stickers_used/. Without this branch strip_tags() drops the
        # <img> and a sticker becomes an EMPTY text message (in one real export that was
        # ~3% of all messages). Stickers and GIFs share one display type.
        subtype = "photo" if "/photos/" in m.group(1) else "gif"
        return subtype, strip_tags(content_html), m.group(1)

    m = AUDIO_SRC_RE.search(content_html)
    if m and "/audio/" in (m.group(1) or m.group(2) or ""):
        return "audio", strip_tags(content_html), (m.group(1) or m.group(2))

    m = FILE_HREF_RE.search(content_html)
    if m:
        # Document attachments (pdf/docx/zip...) are an <a href> to .../files/, not an
        # <img>; without this they also end up as text with the path lost.
        return "file", strip_tags(content_html), m.group(1)

    text = strip_tags(content_html)
    if re.match(r'^你傳送了\s*\d+\s*個附件', text) or (
        "傳送了" in text and "附件" in text and "http" in text
    ):
        return "link", text, None
    return "text", text, None


# ------------------------------------------------------- group system events --
# Group system events (added / left / renamed / photo / admin) use the SAME timeline
# template as normal messages (h2 = actor, footer = timestamp); classify_and_clean()
# returns them as plain text. This is a rule-based second pass, not a new parser.
GROUP_EVENT_PATTERNS = [
    ("member_added", re.compile(r"^(?P<actor>.+?)將(?P<target>.+?)加入了群組。?$")),
    ("member_left", re.compile(r"^(?P<actor>.+?)退出了(?:此|這個)?群組。?$")),
    ("name_changed", re.compile(r"^(?P<actor>.+?)將群組(?:名稱)?命名為(?P<target>.+?)。?$")),
    ("name_removed", re.compile(r"^(?P<actor>.+?)移除(?:了)?群組名稱。?$")),
    ("photo_changed", re.compile(r"^(?P<actor>.+?)變更了群組相片。?$")),
    ("photo_removed", re.compile(r"^(?P<actor>.+?)移除(?:了)?群組(?:大頭貼|相片)。?$")),
    ("admin_added", re.compile(r"^(?P<actor>.+?)將(?P<target>.+?)新增為群組管理員。?$")),
    ("admin_removed", re.compile(r"^(?P<actor>.+?)移除(?P<target>.+?)的群組管理員身分。?$")),
]
# Length guard: a few messages (e.g. shared contact cards with nested HTML) can swallow
# the next message's timestamp text, and the regex above then "matches" a whole noisy
# sentence. Real person names are short, so cap them...
MAX_PLAUSIBLE_NAME_LEN = 20
# ...but GROUP names (the target of name_changed) are often longer than 20 characters.
# Applying the person-name cap to them silently drops real rename events. Give group
# names their own cap and instead reject targets that contain an export timestamp.
MAX_PLAUSIBLE_GROUP_NAME_LEN = 100
EMBEDDED_TS_RE = re.compile(r'\d{1,2} 月 \d{1,2}, \d{4} \d{1,2}:\d{2}(?::\d{2})?')


def classify_group_event(text):
    """{"event_type", "actor", "target"} for a group system sentence, else None."""
    text = (text or "").strip()
    if not text:
        return None
    for event_type, pattern in GROUP_EVENT_PATTERNS:
        m = pattern.match(text)
        if m:
            groups = m.groupdict()
            actor = groups.get("actor", "").strip()
            target = (groups.get("target") or "").strip() or None
            target_max = MAX_PLAUSIBLE_GROUP_NAME_LEN if event_type == "name_changed" else MAX_PLAUSIBLE_NAME_LEN
            if len(actor) > MAX_PLAUSIBLE_NAME_LEN or (target and len(target) > target_max):
                continue
            if target and event_type == "name_changed" and EMBEDDED_TS_RE.search(target):
                continue
            return {"event_type": event_type, "actor": actor, "target": target}
    return None


# ------------------------------------------------------- participant list --
_NAME_NOISE_RE = re.compile(r"[‎‏‪-‮\s]+")


def _norm_name(s):
    """For comparison only: drop direction marks (U+200E etc.) and collapse spaces."""
    return _NAME_NOISE_RE.sub(" ", s or "").strip()


def split_participants(header, known=None, selves=None):
    """「參與者：A、 B、C和 D」-> ["A", "B", "C", "D"] (duplicates such as 「Facebook 用戶」 kept).

    The export separates names with 「、」 but joins the LAST one with 「和」 ("and"),
    with no separator you can trust: a real name may itself contain 和. So only split
    the LAST item at its LAST 和, and only when you can prove it:
      - the right half is in ``known`` (pass: senders actually seen in this thread
        ∪ the user's own aliases), or
      - the left half is one of ``selves`` (the "<me>和 X" form, where X never spoke).
    Otherwise leave it unsplit. Without ``known``/``selves`` nothing is split."""
    body = re.split(r"[:：]", header, maxsplit=1)[1] if re.search(r"[:：]", header) else ""
    parts = [p.strip() for p in body.split("、") if p.strip()]
    if (known or selves) and parts and "和" in parts[-1]:
        left, right = parts[-1].rsplit("和", 1)
        right_ok = bool(known) and _norm_name(right) in {_norm_name(k) for k in known}
        left_ok = bool(selves) and _norm_name(left) in {_norm_name(k) for k in selves}
        if left.strip() and right.strip() and (right_ok or left_ok):
            parts[-1:] = [left.strip(), right.strip()]
    return parts


def thread_title(message_1_path):
    """Get the conversation's display title from message_1.html's <title>
    (more reliable than the folder slug, especially for non-ASCII names)."""
    try:
        raw = read_text(message_1_path)
    except OSError:
        return None
    m = TITLE_RE.search(raw)
    return html.unescape(m.group(1)).strip() if m else None


_MEDIA_ANY_RE = re.compile(
    r'<(?:img|video|audio|source)[^>]*\bsrc="(?P<src>[^"]+)"'
    r'|<a[^>]*\bhref="(?P<href>your_facebook_activity/[^"]+)"'
)


def extract_media_paths(content_html):
    """Every attachment path inside this HTML that points into the export itself
    (deduplicated, order kept). External URLs (http/https/data) are skipped.
    classify_and_clean() returns only the first attachment; this returns all."""
    out = []
    for m in _MEDIA_ANY_RE.finditer(content_html or ""):
        p = html.unescape(m.group("src") or m.group("href") or "")
        if not p or p.startswith(("http:", "https:", "data:", "//")):
            continue
        if p not in out:
            out.append(p)
    return out


def iter_messages(path, stats=None):
    """Yield one message dict at a time (generator — never keeps the whole
    batch in memory), for streaming full-corpus aggregation over thousands of
    message_N.html files. Dict fields: dt, sender, type, text, media_path, media.

    stats (optional dict) accumulates sections / skipped_header / skipped_ts /
    embedded_sections, so the caller can see how many sections were skipped
    instead of losing them silently.

    Sections without a sender (no aria-labelledby, see EMBEDDED_SECTION_RE) are
    split out of the previous message and each emitted as its own record with
    sender=None, type="system" — even when empty, so section accounting
    balances. The previous message keeps only its own content and its own
    (first) footer timestamp. Before this fix, its text ended with a stray
    timestamp or a system sentence, and its dt jumped to the system section's
    time. Keep "message_count" meaning messages WITH a sender; count system
    records separately."""
    raw = read_text(path)
    chunks = SECTION_SPLIT_RE.split(raw)[1:]
    if stats is not None:
        stats["sections"] = stats.get("sections", 0) + len(chunks)
    for chunk in chunks:
        m = HEADER_RE.match(chunk)
        if not m:
            if stats is not None:
                stats["skipped_header"] = stats.get("skipped_header", 0) + 1
            continue
        pieces = EMBEDDED_SECTION_RE.split(m.group("content"))
        piece_texts = pieces[0::2]                        # [own content, embedded 1, embedded 2, ...]
        raw_ts = pieces[1::2] + [m.group("ts")]      # each piece's own timestamp
        if stats is not None and len(piece_texts) > 1:
            stats["embedded_sections"] = stats.get("embedded_sections", 0) + len(piece_texts) - 1
        for i, (content, ts_raw) in enumerate(zip(piece_texts, raw_ts)):
            ts = parse_ts(ts_raw)
            if ts is None:
                if stats is not None:
                    stats["skipped_ts"] = stats.get("skipped_ts", 0) + 1
                continue
            if i == 0:
                msg_type, text, media_path = classify_and_clean(content)
                sender = html.unescape(m.group("sender")).strip()
            else:
                if content.startswith(CONTENT_DIV_OPEN):
                    content = content[len(CONTENT_DIV_OPEN):]
                media = extract_media_paths(content)
                msg_type, text, media_path = SYSTEM_TYPE, strip_tags(content), (media[0] if media else None)
                sender = None
            yield {
                "dt": ts,
                "sender": sender,
                "type": msg_type,
                "text": text,
                "media_path": media_path,
                "media": extract_media_paths(content),
            }


# ------------------------------------------------------- message file discovery --

# When the full path is too long, Meta truncates the file name from the end (the
# ".html" suffix survives): message_.html, message.html, messag.html, ..., m.html,
# even just ".html". A strict r"message_\d+\.html" skips those threads WITHOUT ANY
# ERROR, and an inference-based coverage check ("deep enough = read") still passes.
# So: any file directly in a thread folder whose stem is a prefix of "message_<N>"
# (including an empty stem) is a message page; a missing N means page 1 (several
# pages truncated to the same name overwrite each other, so only one survives).
MESSAGE_FILE_RE = re.compile(r"^(?:m(?:e(?:s(?:s(?:a(?:g(?:e(?:_(\d*))?)?)?)?)?)?)?)?\.html$")
FULL_MESSAGE_FILE_RE = re.compile(r"^message_\d+\.html$")


def message_page(name):
    """message_N.html -> N; truncated names (message_.html, mes.html, .html, ...) -> 1;
    anything else -> None."""
    m = MESSAGE_FILE_RE.match(name)
    if not m:
        return None
    return int(m.group(1)) if m.group(1) else 1


def is_truncated_message_name(name):
    """A message page whose name was truncated by Meta (not a full message_N.html)."""
    return message_page(name) is not None and not FULL_MESSAGE_FILE_RE.match(name)


def find_message_files(thread_dir):
    """Message pages directly inside thread_dir (truncated names included), sorted
    by page number. Record the returned list (and the truncated subset) in the
    extractor's manifest, e.g. extra.message_files / extra.truncated_message_files,
    so the coverage check can compare against what was actually read."""
    files = []
    for f in thread_dir.iterdir():
        if not f.is_file():
            continue
        page = message_page(f.name)
        if page is not None:
            files.append((page, f.name, f))
    return [f for _, _, f in sorted(files)]


# ------------------------------------------------------- self-test --

def _self_test():
    """Run with `python fb_common.py`. Uses made-up HTML fragments and names only."""
    import tempfile
    from pathlib import Path

    def msg(sender, body, ts, label="x"):
        return (f'<section class="_a6-g" aria-labelledby="{label}"><h2 class="_2ph_ _a6-h _a6-i" id="{label}">'
                f'{sender}</h2><div class="_2ph_ _a6-p">{body}</div><footer class="_3-94 _a6-o">'
                f'<div class="_a72d">{ts}</div></footer></section>')

    def embedded(body, ts):
        return (f'<section class="_a6-g"><div class="_2ph_ _a6-p">{body}</div><footer class="_3-94 _a6-o">'
                f'<div class="_a72d">{ts}</div></footer></section>')

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)

        # 1. plain messages unchanged
        p = d / "message_1.html"
        p.write_text("<html><body>" + msg("Person A", "<div>hello</div>", "7 月 19, 2017 10:00:51 下午", "a")
                     + msg("Person B", "<div>hi</div>", "7 月 19, 2017 9:43:40 下午", "b") + "</body></html>",
                     encoding="utf-8")
        rows = list(iter_messages(p))
        assert [(r["sender"], r["type"], r["text"]) for r in rows] == [
            ("Person A", "text", "hello"), ("Person B", "text", "hi")], rows
        assert rows[0]["dt"].isoformat() == "2017-07-19T22:00:51"

        # 2. unlabelled sections are split out as system records
        body = (msg("Person A", "<div>own text</div>", "4 月 01, 2017 6:22:00 下午", "a")
                + embedded("<div><div></div></div>", "4 月 01, 2017 6:21:00 下午")
                + embedded('<div><div>Person C added Person D.</div><img src="your_facebook_activity/messages/x/photos/1.jpg"></div>',
                           "4 月 01, 2017 6:20:00 下午"))
        p.write_text("<html><body>" + body + "</body></html>", encoding="utf-8")
        stats = {}
        first, empty, sysmsg = list(iter_messages(p, stats))
        assert (first["sender"], first["type"], first["text"]) == ("Person A", "text", "own text"), first
        assert first["dt"].isoformat() == "2017-04-01T18:22:00", first["dt"]
        assert (empty["sender"], empty["type"], empty["text"]) == (None, "system", ""), empty
        assert (sysmsg["sender"], sysmsg["type"], sysmsg["text"]) == (None, "system", "Person C added Person D."), sysmsg
        assert sysmsg["media"] == ["your_facebook_activity/messages/x/photos/1.jpg"], sysmsg
        assert stats == {"sections": 1, "embedded_sections": 2}, stats

        # 3. truncated message file names
        truncated = [".html", "m.html", "me.html", "mes.html", "mess.html", "messa.html", "messag.html",
                     "message.html", "message_.html"]
        for name in truncated:
            assert message_page(name) == 1 and is_truncated_message_name(name), name
        for name in ["message_1.htm", "messages.html", "metaai_1.html", "photo.jpg", "x.html", "mx.html",
                     "message_a.html", "someone_123.html", "message_1.html.bak"]:
            assert message_page(name) is None, name
        assert message_page("message_12.html") == 12 and not is_truncated_message_name("message_12.html")
        for name in truncated:
            td = d / ("t" + name.replace(".", "_"))
            td.mkdir()
            (td / name).write_text("x", encoding="utf-8")
            (td / "photos").mkdir()
            (td / "readme.txt").write_text("x", encoding="utf-8")
            assert [f.name for f in find_message_files(td)] == [name], name
        td = d / "multi"
        td.mkdir()
        for n in ("message_10.html", "message_2.html", "message_1.html"):
            (td / n).write_text("x", encoding="utf-8")
        assert [f.name for f in find_message_files(td)] == ["message_1.html", "message_2.html", "message_10.html"]

        # 4. U+2028 inside message text survives a JSONL round trip
        jp = d / "out.jsonl"
        write_jsonl(jp, [{"text": "line one still the same message"}, {"text": "second"}])
        assert len(jp.read_text(encoding="utf-8").splitlines()) == 3   # the trap: splitlines sees 3 lines
        recs = list(iter_jsonl(jp))
        assert [r["text"] for r in recs] == ["line one still the same message", "second"], recs

    # 5. stickers and document attachments are not lost as empty text
    t, _, mp = classify_and_clean('<div><img src="your_facebook_activity/messages/stickers_used/123.png"></div>')
    assert (t, mp) == ("gif", "your_facebook_activity/messages/stickers_used/123.png"), (t, mp)
    t, _, mp = classify_and_clean('<div><a href="your_facebook_activity/messages/inbox/x_1/files/notes.pdf">notes.pdf</a></div>')
    assert (t, mp) == ("file", "your_facebook_activity/messages/inbox/x_1/files/notes.pdf"), (t, mp)
    t, _, _ = classify_and_clean('<div><a href="https://example.edu/courses/1/files/2">link</a></div>')
    assert t == "text", t

    # 6. long group names are still rename events; timestamp noise is rejected
    long_name = "Weekend Hiking Club Official Chat Room Version Two"      # > 20 chars
    ev = classify_group_event(f"Person A將群組命名為{long_name}。")
    assert ev and ev["event_type"] == "name_changed" and ev["target"] == long_name, ev
    assert classify_group_event("Person A將群組命名為x 7 月 18, 2018 9:47:55 上午1 位聯絡人") is None
    assert classify_group_event("Person A將Person B加入了群組。")["event_type"] == "member_added"
    assert classify_group_event("A" * 21 + "將Person B加入了群組。") is None   # person-name cap unchanged

    # 7. participant list: split the last 「和」 only when it can be proven
    h = "參與者：Person A、 Person B和 Person C"
    assert split_participants(h) == ["Person A", "Person B和 Person C"]
    assert split_participants(h, known={"Person C"}) == ["Person A", "Person B", "Person C"]
    assert split_participants("參與者：Me和 Stranger", selves={"Me"}) == ["Me", "Stranger"]
    assert split_participants("參與者：Person A、 Lin 和平", known={"Person A"}) == ["Person A", "Lin 和平"]

    print("fb_common self-test: PASS")


if __name__ == "__main__":
    _self_test()
