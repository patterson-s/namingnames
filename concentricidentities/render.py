#!/usr/bin/env python3
"""Reading-pane renderer for the concentric-identity console.

Adapted from 13july2026/review_render.py. The speech is rendered as ONE
self-contained HTML document embedded via an iframe, so in-iframe JavaScript can
do a smooth-scrolling reading column, a margin minimap, evidence-quote
highlighting, and a colour-matched pulse when a quote is focused.

Difference from the sibling: there are no NER "target" spans — only evidence
quotes — and colour is keyed by the claim's `scope_type`, not a four-point label.
"""

import html
import json
from typing import Any, Dict, List, Optional, Tuple

from highlight import dedupe_spans

Span = Tuple[int, int]

SCOPE_TYPES = ["regional", "values", "role", "ideological", "economic", "other"]


def _overlap(a: Span, b: Span) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def scope_class(scope_type: Optional[str]) -> str:
    if scope_type in SCOPE_TYPES:
        return f"sc-{scope_type}"
    return "sc-other"


def assemble_spans(speech_text: str, groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve evidence-quote spans across all claim cards into rendered speech
    HTML, minimap ticks, and a per-card jump target.

    Each group: {card_id, scope_type, quote_spans: [(s, e), ...]}.
    Returns: speech_html, ticks_html, card_jump {card_id -> span_id}.
    """
    text_len = max(len(speech_text), 1)

    all_quotes = dedupe_spans([s for g in groups for s in g["quote_spans"]])
    ordered = sorted(all_quotes)

    span_id: Dict[Span, str] = {}
    for i, span in enumerate(ordered):
        span_id[span] = f"sp{i}"

    # plurality scope_type per span (colours the highlight)
    span_scopes: Dict[Span, List[str]] = {s: [] for s in ordered}
    for g in groups:
        for s in ordered:
            if any(_overlap(s, q) for q in g["quote_spans"]):
                span_scopes[s].append(g["scope_type"])

    def _plurality(scopes: List[str]) -> Optional[str]:
        return max(set(scopes), key=scopes.count) if scopes else None

    # per-card jump target: first (document-order) quote span it overlaps
    card_jump: Dict[str, str] = {}
    for g in groups:
        chosen = ""
        for s in ordered:
            if any(_overlap(s, q) for q in g["quote_spans"]):
                chosen = span_id[s]
                break
        card_jump[g["card_id"]] = chosen

    out: List[str] = []
    ticks: List[str] = []
    pos = 0
    for s, e in ordered:
        if s < pos:
            continue
        out.append(html.escape(speech_text[pos:s]))
        seg = html.escape(speech_text[s:e])
        sid = span_id[(s, e)]
        sc = scope_class(_plurality(span_scopes[(s, e)]))
        out.append(f'<span id="{sid}" class="quote {sc}">{seg}</span>')
        frac = (s / text_len) * 100.0
        ticks.append(
            f'<button class="tick {sc}" style="top:{frac:.3f}%" '
            f"title=\"jump to quote\" onclick=\"jump('{sid}')\"></button>"
        )
        pos = e
    out.append(html.escape(speech_text[pos:]))
    speech_html = "".join(out).replace("\n\n", "</p><p>").replace("\n", "<br>")
    speech_html = f"<p>{speech_html}</p>"

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
  --sc-regional:#1f8a70;   --sc-values:#6d4bd0;   --sc-role:#2f5fd0;
  --sc-ideological:#c0392b; --sc-economic:#b8791f; --sc-other:#6b7280;
  --ink:#20242e; --ink-soft:#565d6a;
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
  background:var(--sc-other);
}}
.tick:hover {{ opacity:1; transform:scale(1.6); }}
.tick.sc-regional {{ background:var(--sc-regional); }}
.tick.sc-values {{ background:var(--sc-values); }}
.tick.sc-role {{ background:var(--sc-role); }}
.tick.sc-ideological {{ background:var(--sc-ideological); }}
.tick.sc-economic {{ background:var(--sc-economic); }}
.tick.sc-other {{ background:var(--sc-other); }}

.speech {{
  font-family:'Newsreader',serif; font-size:18.5px; line-height:1.72;
  color:#23262d; max-width:60ch;
}}
.speech p {{ margin:0 0 1.1em 0; }}
.quote {{
  padding:0 1px; border-radius:2px; scroll-margin:40vh;
  border-bottom:2px solid var(--sc-other); --pulse:var(--sc-other);
}}
.quote.sc-regional    {{ border-color:var(--sc-regional);    background:rgba(31,138,112,.10);  --pulse:var(--sc-regional); }}
.quote.sc-values      {{ border-color:var(--sc-values);      background:rgba(109,75,208,.10);  --pulse:var(--sc-values); }}
.quote.sc-role        {{ border-color:var(--sc-role);        background:rgba(47,95,208,.10);   --pulse:var(--sc-role); }}
.quote.sc-ideological {{ border-color:var(--sc-ideological); background:rgba(192,57,43,.10);   --pulse:var(--sc-ideological); }}
.quote.sc-economic    {{ border-color:var(--sc-economic);    background:rgba(184,121,31,.11);  --pulse:var(--sc-economic); }}
.quote.sc-other       {{ border-color:var(--sc-other);       background:rgba(107,114,128,.10); --pulse:var(--sc-other); }}
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
  function jump(id) {{
    const e = document.getElementById(id); if (!e) return;
    e.scrollIntoView({{behavior:'smooth', block:'center'}});
    pulse(id);
  }}
  window.addEventListener('DOMContentLoaded', function() {{
    if (FOCUS) {{
      const e = document.getElementById(FOCUS);
      if (e) {{ e.scrollIntoView({{block:'center'}}); pulse(FOCUS); }}
    }}
  }});
</script>
</body></html>"""
