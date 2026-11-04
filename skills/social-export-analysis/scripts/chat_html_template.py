# -*- coding: utf-8 -*-
"""
Template: render one conversation thread's messages as a scrollable, iMessage-
style chat transcript (`chat.html`) — self/other bubbles on opposite sides,
media inlined, one optional "context note" banner for edge-case threads.

Extracted from a Facebook-export project (Account A, 2026-09-22) after
porting this exact bubble UI from a sibling project (Account B) that already
had it. Parts marked "ADAPT" are project-specific; everything else (bubble
CSS shape, self/other class logic, media-path resolution, special-note
mechanism) is reusable as-is.

Copy into <project>/analysis/scripts/<messages-or-similar>/, wire the
CSS block below into that project's `analysis/output/assets/shared.css`
(append once, shared by every chat.html — don't inline a full copy per file,
that's what the original Account B version did and it's needlessly repetitive
across hundreds of files), then call build_chat_html() per thread the same
way you already loop over thread_index.json.

Standard library only (besides your project's own fb_common-style connector,
which must yield dicts shaped {"dt", "sender", "type", "text", "media_path"}
— see social-export-analysis's connectors/facebook_html/fb_common.py).
"""
import html as html_mod
import os
from pathlib import Path

# ---- ADAPT: who counts as "self" (bubble goes right / accent color) ----
# Keep this as a single set your whole project imports, not copy-pasted into
# every module that needs a self/other check (the Account A project had it
# duplicated in 4 separate config.py/extract_*.py files before this pass —
# don't repeat that mistake in a fresh project).
SELF_NAMES = {"Your Name Here"}

# ---- ADAPT: per-thread context banners for edge cases ----
# Real-world use case this was built for: the export contains a thread with
# what LOOKS like a second person, but is actually the same human's other
# account (a rename/migration/second-account situation). Decision made for
# that case: DON'T fold the other name into SELF_NAMES (that would collapse
# the conversation into all-self bubbles and hide the back-and-forth shape);
# instead keep normal left/right rendering and inject one explanatory note
# so a reader immediately understands both sides are the same person.
# Key by whatever uniquely identifies a thread in your thread_index (here:
# (category, thread_id) tuple, matching Facebook's own thread_index shape).
SPECIAL_THREAD_NOTES = {
    # ("e2ee_cutover", "somenumericid"): "Explanation shown as a banner...",
}


def render_msg_body(m: dict, thread_dir: Path, raw_root: Path) -> str:
    """m is one message dict: {"dt", "sender", "type", "text", "media_path"}.
    thread_dir is this thread's own source folder (where chat.html's sibling
    photos/gifs/videos/audio/files folders were hardlinked FROM)."""
    media_path = m.get("media_path")
    if m["type"] == "unsent":
        return '<span class="msg-unsent">（已收回）</span>'
    if media_path:
        # GOTCHA (cost ~30min to find): the raw export's <img src="...">
        # attribute is typically relative to the EXPORT ROOT, not to the
        # thread's own folder — e.g. "your_facebook_activity/messages/
        # <category>/<thread_id>/photos/x.jpg", even though the HTML file
        # containing that <img> tag lives deep inside that same thread
        # folder. If you write that string straight into chat.html's <img
        # src>, it 404s, because chat.html sits next to a hardlinked
        # photos/ folder (NOT next to a your_facebook_activity/ tree) —
        # the hardlink step only mirrors the thread's OWN subtree, not the
        # whole export. Always resolve to an absolute path first, then
        # re-relativize against the thread folder chat.html actually lives
        # beside:
        abs_media = (raw_root / media_path).resolve()
        rel_media = os.path.relpath(abs_media, thread_dir).replace(os.sep, "/")
        src = html_mod.escape(rel_media, quote=True)
        if m["type"] in ("photo", "gif"):
            return f'<img src="{src}" alt="" loading="lazy">'
        if m["type"] == "media":
            return f'<video controls preload="none" src="{src}"></video>'
        if m["type"] == "audio":
            return f'<audio controls preload="none" src="{src}"></audio>'
    text = html_mod.escape(m["text"]) if m.get("text") else ""
    return text if text else "（無內容）"


def build_chat_html(thread_dir: Path, raw_root: Path, title: str, out_path: Path,
                     is_group: bool, category: str, thread_id: str,
                     iter_messages) -> int:
    """iter_messages: your connector's generator over this thread's raw
    message files, yielding dicts shaped like render_msg_body() expects
    (see social-export-analysis's fb_common.iter_messages for reference)."""
    rows = []
    senders = set()
    for m in iter_messages(thread_dir):
        senders.add(m["sender"])
        is_self = m["sender"] in SELF_NAMES
        sender = html_mod.escape(m["sender"])
        ts = m["dt"].strftime("%Y-%m-%d %H:%M")
        body_html = render_msg_body(m, thread_dir, raw_root)
        css_class = "msg msg-self" if is_self else "msg msg-other"
        rows.append(
            f'<div class="{css_class}"><div class="msg-meta">'
            f'<span class="sender">{sender}</span><span class="ts">{ts}</span>'
            f'</div><div class="msg-body">{body_html}</div></div>'
        )

    special_note = SPECIAL_THREAD_NOTES.get((category, thread_id))
    note_html = (f'<div class="note self-note">{html_mod.escape(special_note)}</div>'
                 if special_note else "")

    # ADAPT: relative path from chat.html's own folder to your shared.css —
    # depends on how deep derived/<kind>/<slug>/chat.html sits below your
    # project root.
    html_out = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(title)}</title>
<link rel="stylesheet" href="../../../analysis/output/assets/shared.css">
</head>
<body>
<header>
<nav class="crumbs"><a href="../../../analysis/output/messages/report.html">← back to index</a></nav>
<h1>{html_mod.escape(title)}</h1>
<p>{"group" if is_group else "1:1"}</p>
</header>
<div class="stats-bar">
<div class="stat"><div class="num">{len(rows)}</div><div class="label">messages</div></div>
<div class="stat"><div class="num">{len(senders)}</div><div class="label">participants</div></div>
</div>
<section>
{note_html}
<div class="media-toggle"><label><input type="checkbox" id="mediaToggle" onchange="fbToggleMedia()"> hide media</label></div>
<div class="msg-list">{''.join(rows)}</div>
</section>
<script>
function fbToggleMedia(){{
  var hide = document.getElementById('mediaToggle').checked;
  document.querySelectorAll('.msg-list').forEach(function(el){{ el.classList.toggle('hide-media', hide); }});
  localStorage.setItem('fbHideMedia', hide ? '1' : '0');
}}
document.addEventListener('DOMContentLoaded', function(){{
  var cb = document.getElementById('mediaToggle');
  if(cb && localStorage.getItem('fbHideMedia') === '1'){{
    cb.checked = true;
    fbToggleMedia();
  }}
}});
</script>
</body>
</html>"""
    out_path.write_text(html_out, encoding="utf-8")
    return len(rows)


# ---------------------------------------------------------------------------
# CSS block to append ONCE to <project>/analysis/output/assets/shared.css
# (not inlined per chat.html — hundreds of files duplicating the same ~20
# lines is the mistake the original reference implementation made).
# Assumes shared.css already defines the base design tokens this skill's
# report templates use: --card, --accent, --border, --muted, plus a `.note`
# class. If your project's shared.css doesn't have those yet, add them too
# (see any *_report_template.py in this skill for the full :root block).
# ---------------------------------------------------------------------------
CHAT_BUBBLE_CSS = """
  .msg-list { display:flex; flex-direction:column; gap:10px; max-width:760px; margin:0 auto; }
  .msg { max-width:72%; background:var(--card); border:1px solid var(--border); border-radius:12px; padding:10px 14px; align-self:flex-start; }
  .msg.msg-self { align-self:flex-end; background:rgba(3,105,161,0.12); border-color:rgba(3,105,161,0.30); }
  .msg-meta { display:flex; justify-content:space-between; gap:12px; font-size:12px; color:var(--muted); margin-bottom:4px; }
  .msg.msg-self .msg-meta { flex-direction:row-reverse; }
  .msg-meta .sender { font-weight:600; color:var(--accent); }
  .msg-body { font-size:14px; line-height:1.6; white-space:pre-wrap; word-break:break-word; }
  .msg-body img { max-width:280px; max-height:280px; border-radius:8px; display:block; }
  .msg-body video { max-width:360px; border-radius:8px; display:block; }
  .msg-body audio { width:280px; }
  .msg-body a.file-link { color:var(--accent); }
  .msg-unsent, .msg-missing { color:var(--muted); font-style:italic; white-space:normal; }
  .media-toggle { text-align:center; margin:0 0 16px; font-size:13px; color:var(--muted); }
  .media-toggle input { margin-right:6px; vertical-align:middle; }
  .msg-list.hide-media .msg-body img, .msg-list.hide-media .msg-body video { display:none; }
  .note.self-note { max-width:760px; margin:0 auto 20px; }
"""
