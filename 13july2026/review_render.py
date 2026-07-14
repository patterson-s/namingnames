#!/usr/bin/env python3
"""Reading-pane renderer for the annotation console.

The speech is rendered as ONE self-contained HTML document embedded via
st.components.v1.html, so in-iframe JavaScript can do what Streamlit markdown
cannot: a smooth-scrolling reading column, a margin minimap, mention + quote
highlighting, and a colour-matched pulse when a mention is focused.

The assessment cards live OUTSIDE this iframe as native Streamlit widgets
(so their review controls can persist to Postgres). Cross-boundary
click-through works by rebuilding this iframe with `focus_span_id`, which the
on-load script scrolls to and pulses.
"""

import html
import json
from typing import List, Tuple, Dict, Any, Optional

from highlight import dedupe_spans

Span = Tuple[int, int]

LABEL_ORDER = ["confrontation", "competition", "cooperation", "indifference"]


def _overlap(a: Span, b: Span) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def _merge_spans(spans: List[Span]) -> List[Span]:
    """Merge overlapping/adjacent spans into a minimal non-overlapping, sorted
    set. Used for chunk regions: several model cards cite the same chunk, so
    their chunk spans collapse to one highlighted passage."""
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [list(ordered[0])]
    for a, b in ordered[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _label_class(label: Optional[str]) -> str:
    if label in LABEL_ORDER:
        return f"lbl-{label}"
    return "lbl-none"


def assemble_spans(speech_text: str, groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve mention + quote spans across all cards into rendered speech HTML,
    minimap ticks, and a per-card jump target.

    Returns dict with:
      speech_html : str  — speech with <span id="spN" ...> wrapping
      ticks_html  : str  — minimap tick buttons
      card_jump   : dict[card_id -> span_id]  — first mention span per card
    """
    text_len = max(len(speech_text), 1)

    all_targets = dedupe_spans([s for g in groups for s in g["target_spans"]])
    all_quotes = [
        q
        for q in dedupe_spans([s for g in groups for s in g["quote_spans"]])
        if not any(_overlap(q, t) for t in all_targets)
    ]

    ordered = sorted(
        [(s, e, "target") for s, e in all_targets]
        + [(s, e, "quote") for s, e in all_quotes]
    )
    span_id: Dict[Span, str] = {}
    span_kind: Dict[Span, str] = {}
    for i, (s, e, kind_) in enumerate(ordered):
        span_id[(s, e)] = f"sp{i}"
        span_kind[(s, e)] = kind_

    # plurality label per target span (colours the mention)
    target_labels: Dict[Span, List[str]] = {
        (s, e): [] for s, e, k in ordered if k == "target"
    }
    for g in groups:
        for s, e, k in ordered:
            if k == "target" and any(_overlap((s, e), t) for t in g["target_spans"]):
                if g.get("label"):
                    target_labels[(s, e)].append(g["label"])

    def _plurality(labels: List[str]) -> Optional[str]:
        return max(set(labels), key=labels.count) if labels else None

    # per-card jump target: first (document-order) target span it overlaps,
    # else first quote span it overlaps
    card_jump: Dict[str, str] = {}
    for g in groups:
        cid = g["card_id"]
        chosen = ""
        for s, e, k in ordered:  # ordered is document order
            if k == "target" and any(_overlap((s, e), t) for t in g["target_spans"]):
                chosen = span_id[(s, e)]
                break
        if not chosen:
            for s, e, k in ordered:
                if k == "quote" and any(_overlap((s, e), q) for q in g["quote_spans"]):
                    chosen = span_id[(s, e)]
                    break
        card_jump[cid] = chosen

    # chunk regions: the full cited passage behind each mention, so several
    # mentions of the same target read as one bounded excerpt. Overlapping
    # chunks (same passage cited by different model cards) collapse into one.
    regions = _merge_spans([g["chunk_span"] for g in groups if g.get("chunk_span")])

    # render speech + ticks via an event stream so chunk-region spans can be
    # closed and reopened across paragraph breaks (a raw <span> straddling
    # </p><p> would be silently severed by the browser).
    events: List[Tuple[int, int, str, Any]] = []
    for rs, re_ in regions:
        events.append((rs, 2, "ropen", None))
        events.append((re_, 1, "rclose", None))
    for s, e, k in ordered:
        events.append((s, 3, "iopen", (s, e, k)))
        events.append((e, 0, "iclose", None))
    events.sort(key=lambda ev: (ev[0], ev[1]))

    out: List[str] = []
    ticks: List[str] = []
    open_stack: List[str] = []  # reopen-HTML for tags open across a paragraph break

    def emit_text(seg: str) -> None:
        parts = seg.split("\n\n")
        for i, part in enumerate(parts):
            out.append(html.escape(part).replace("\n", "<br>"))
            if i < len(parts) - 1:  # paragraph break: re-wrap open spans around it
                out.extend("</span>" for _ in open_stack)
                out.append("</p><p>")
                out.extend(open_stack)

    pos = 0
    for p, _prio, typ, data in events:
        if p > pos:
            emit_text(speech_text[pos:p])
            pos = p
        if typ == "ropen":
            out.append('<span class="chunk-region">')
            open_stack.append('<span class="chunk-region">')
        elif typ == "rclose":
            out.append("</span>")
            open_stack.pop()
        elif typ == "iopen":
            s, e, k = data
            sid = span_id[(s, e)]
            if k == "target":
                lc = _label_class(_plurality(target_labels[(s, e)]))
                out.append(f'<span id="{sid}" class="mention {lc}">')
                open_stack.append(f'<span class="mention {lc}">')  # reopen sans id
                frac = (s / text_len) * 100.0
                ticks.append(
                    f'<button class="tick {lc}" style="top:{frac:.3f}%" '
                    f"title=\"jump to mention\" onclick=\"jump('{sid}')\"></button>"
                )
            else:
                out.append(f'<span id="{sid}" class="quote">')
                open_stack.append('<span class="quote">')
        elif typ == "iclose":
            out.append("</span>")
            open_stack.pop()
    emit_text(speech_text[pos:])

    speech_html = f"<p>{''.join(out)}</p>"

    return {"speech_html": speech_html, "ticks_html": "".join(ticks), "card_jump": card_jump}


def build_reading_html(
    *,
    source: str,
    year: Any,
    heading: str,
    speech_html: str,
    ticks_html: str,
    focus_span_id: Optional[str] = None,
    height_px: int = 760,
) -> str:
    """Self-contained reading-pane iframe. If focus_span_id is given, the pane
    scrolls to that span and pulses it on load."""
    year_str = html.escape(str(year)) if year is not None else ""
    return _DOC_TEMPLATE.format(
        source=html.escape(source),
        year=year_str,
        heading=html.escape(heading),
        ticks=ticks_html,
        speech=speech_html,
        focus=json.dumps(focus_span_id),
        height=height_px,
    )


_DOC_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --c-confrontation:#c0392b; --c-competition:#b8791f;
  --c-cooperation:#1f8a70;   --c-indifference:#6b7280;
  --c-none:#9aa0a8;
  --ink:#20242e; --ink-soft:#565d6a; --blue:#2f5fd0;
  --paper:#faf9f6; --line:#e2ded5;
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; }}
body {{ font-family:'IBM Plex Sans',system-ui,sans-serif; color:var(--ink); -webkit-font-smoothing:antialiased; }}
.reading {{
  position:relative; height:{height}px; overflow-y:auto; background:var(--paper);
  padding:34px 40px 60px 40px; border-radius:10px;
}}
.reading::-webkit-scrollbar {{ width:11px; }}
.reading::-webkit-scrollbar-thumb {{ background:#d8d3c8; border-radius:6px; border:3px solid var(--paper); }}
.doc-head {{ margin:0 0 22px 0; padding-bottom:16px; border-bottom:1px solid var(--line); }}
.doc-head .code {{
  font-family:'IBM Plex Mono',monospace; font-size:12px; letter-spacing:.04em;
  color:var(--ink-soft); text-transform:uppercase;
}}
.doc-head h1 {{
  font-family:'Newsreader',serif; font-weight:500; font-size:26px;
  line-height:1.15; margin:6px 0 0 0; letter-spacing:-.01em;
}}
.rail {{ position:absolute; top:34px; bottom:60px; left:14px; width:6px; }}
.tick {{
  position:absolute; left:0; width:6px; height:6px; padding:0; border:none;
  border-radius:50%; cursor:pointer; opacity:.55; transition:opacity .15s, transform .15s;
  background:var(--c-none);
}}
.tick:hover {{ opacity:1; transform:scale(1.6); }}
.tick.lbl-confrontation {{ background:var(--c-confrontation); }}
.tick.lbl-competition   {{ background:var(--c-competition); }}
.tick.lbl-cooperation   {{ background:var(--c-cooperation); }}
.tick.lbl-indifference  {{ background:var(--c-indifference); }}
.tick.lbl-none          {{ background:var(--c-none); }}

.speech {{
  font-family:'Newsreader',serif; font-size:18.5px; line-height:1.72;
  color:#23262d; max-width:60ch;
}}
.speech p {{ margin:0 0 1.1em 0; }}
/* Chunk bands are invisible until you jump to one — only the pertinent
   passage lights up, so the reading pane stays calm by default. */
.chunk-region {{
  border-radius:3px; padding:2px 0; transition:background .25s, box-shadow .25s;
  -webkit-box-decoration-break:clone; box-decoration-break:clone;
}}
.chunk-region.active {{
  background:rgba(47,95,208,.15); box-shadow:inset 2px 0 0 rgba(47,95,208,.7);
}}
.mention {{
  padding:0 1px; border-radius:2px; border-bottom:2px solid var(--c-none);
  transition:background .2s; --pulse:var(--blue); scroll-margin:40vh;
  -webkit-box-decoration-break:clone; box-decoration-break:clone;
}}
.mention.lbl-confrontation {{ border-color:var(--c-confrontation); background:rgba(192,57,43,.07); --pulse:var(--c-confrontation); }}
.mention.lbl-competition   {{ border-color:var(--c-competition);  background:rgba(184,121,31,.08); --pulse:var(--c-competition); }}
.mention.lbl-cooperation   {{ border-color:var(--c-cooperation);  background:rgba(31,138,112,.08); --pulse:var(--c-cooperation); }}
.mention.lbl-indifference  {{ border-color:var(--c-indifference); background:rgba(107,114,128,.08); --pulse:var(--c-indifference); }}
.mention.lbl-none          {{ border-color:var(--c-none);         background:rgba(154,160,168,.10); }}
.quote {{
  background:linear-gradient(transparent 62%, rgba(233,196,79,.55) 62%);
  padding:0 1px; scroll-margin:40vh; --pulse:#e9c44f;
}}
@keyframes pulse {{
  0%   {{ box-shadow:0 0 0 0 var(--pulse); background:color-mix(in srgb,var(--pulse) 26%,transparent); }}
  100% {{ box-shadow:0 0 0 10px transparent; }}
}}
.pulsing {{ animation:pulse 1.2s ease-out; }}
</style></head>
<body>
  <section class="reading" id="reading">
    <div class="rail">{ticks}</div>
    <div class="doc-head">
      <div class="code">{source} · {year}</div>
      <h1>{heading}</h1>
    </div>
    <div class="speech">{speech}</div>
  </section>
<script>
  const FOCUS = {focus};
  function pulse(id) {{
    const e = document.getElementById(id); if (!e) return;
    e.classList.remove('pulsing'); void e.offsetWidth; e.classList.add('pulsing');
  }}
  function markRegion(id) {{
    document.querySelectorAll('.chunk-region.active').forEach(r => r.classList.remove('active'));
    const e = document.getElementById(id); if (!e) return;
    const r = e.closest('.chunk-region'); if (r) r.classList.add('active');
  }}
  function jump(id) {{
    const e = document.getElementById(id); if (!e) return;
    e.scrollIntoView({{behavior:'smooth', block:'center'}});
    markRegion(id); pulse(id);
  }}
  window.addEventListener('DOMContentLoaded', function() {{
    if (FOCUS) {{
      const e = document.getElementById(FOCUS);
      if (e) {{ e.scrollIntoView({{block:'center'}}); markRegion(FOCUS); pulse(FOCUS); }}
    }}
  }});
</script>
</body></html>"""
