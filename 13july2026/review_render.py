#!/usr/bin/env python3
"""Self-contained two-pane review surface for the annotation console.

The whole reading column + assessment column is rendered as ONE HTML document
embedded via st.components.v1.html, so in-iframe JavaScript can do what Streamlit
markdown cannot: two independently scrolling columns, click-through from an
assessment card to the mention in the speech, a margin minimap, and pulse-on-jump
highlighting that ties the two columns together by label colour.
"""

import html
from typing import List, Tuple, Dict, Any, Optional

from highlight import dedupe_spans

Span = Tuple[int, int]

LABEL_ORDER = ["confrontation", "competition", "cooperation", "indifference"]


def _overlap(a: Span, b: Span) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


def _label_class(label: Optional[str]) -> str:
    if label in LABEL_ORDER:
        return f"lbl-{label}"
    return "lbl-none"


def _label_text(label: Optional[str]) -> str:
    return label if label else "malformed"


def build_review_html(
    *,
    source: str,
    year: Any,
    heading: str,
    kind: str,
    speech_text: str,
    groups: List[Dict[str, Any]],
    aggregate_html: str = "",
    height_px: int = 760,
) -> str:
    """groups: one dict per assessment card with keys
    card_id, model_name, label (four_point), reasoning, quotes,
    target_spans, quote_spans, claims (identity), malformed."""

    text_len = max(len(speech_text), 1)

    # --- 1. resolve unique spans -------------------------------------------
    all_targets = dedupe_spans([s for g in groups for s in g["target_spans"]])
    all_quotes = [
        q
        for q in dedupe_spans([s for g in groups for s in g["quote_spans"]])
        if not any(_overlap(q, t) for t in all_targets)
    ]

    # stable id per unique span, in document order
    ordered = sorted(
        [(s, e, "target") for s, e in all_targets]
        + [(s, e, "quote") for s, e in all_quotes]
    )
    span_id: Dict[Span, str] = {}
    span_kind: Dict[Span, str] = {}
    for i, (s, e, kind_) in enumerate(ordered):
        span_id[(s, e)] = f"sp{i}"
        span_kind[(s, e)] = kind_

    # which cards reference each span; plurality label per target span
    span_cards: Dict[Span, List[str]] = {(s, e): [] for s, e, _ in ordered}
    target_labels: Dict[Span, List[str]] = {
        (s, e): [] for s, e, k in ordered if k == "target"
    }
    for g in groups:
        cid = g["card_id"]
        for s, e, k in ordered:
            key = (s, e)
            if k == "target" and any(_overlap(key, t) for t in g["target_spans"]):
                span_cards[key].append(cid)
                if g.get("label"):
                    target_labels[key].append(g["label"])
            elif k == "quote" and any(_overlap(key, q) for q in g["quote_spans"]):
                span_cards[key].append(cid)

    def _plurality(labels: List[str]) -> Optional[str]:
        if not labels:
            return None
        return max(set(labels), key=labels.count)

    span_label_class: Dict[Span, str] = {}
    for s, e, k in ordered:
        if k == "target":
            span_label_class[(s, e)] = _label_class(_plurality(target_labels[(s, e)]))

    # --- 2. render speech with wrapped spans -------------------------------
    out: List[str] = []
    ticks: List[str] = []
    pos = 0
    for s, e, k in ordered:
        if s < pos:
            continue
        out.append(html.escape(speech_text[pos:s]))
        seg = html.escape(speech_text[s:e])
        sid = span_id[(s, e)]
        cards_attr = " ".join(dict.fromkeys(span_cards[(s, e)]))
        if k == "target":
            lc = span_label_class[(s, e)]
            out.append(
                f'<span id="{sid}" class="mention {lc}" '
                f'data-cards="{cards_attr}" onclick="fromText(this)">{seg}</span>'
            )
            frac = (s / text_len) * 100.0
            ticks.append(
                f'<button class="tick {lc}" style="top:{frac:.3f}%" '
                f'title="jump to mention" onclick="jump(\'{sid}\', \'\')"></button>'
            )
        else:
            out.append(
                f'<span id="{sid}" class="quote" data-cards="{cards_attr}">{seg}</span>'
            )
        pos = e
    out.append(html.escape(speech_text[pos:]))
    speech_html = "".join(out).replace("\n\n", "</p><p>").replace("\n", "<br>")
    speech_html = f"<p>{speech_html}</p>"

    # --- 3. render assessment cards ----------------------------------------
    cards_html: List[str] = []
    for g in groups:
        cid = g["card_id"]
        my_spans = [span_id[k] for k in span_id if cid in span_cards.get(k, [])]
        my_targets = [
            span_id[k]
            for k in span_id
            if cid in span_cards.get(k, []) and span_kind[k] == "target"
        ]
        jump_id = my_targets[0] if my_targets else (my_spans[0] if my_spans else "")

        if g.get("kind") == "identity" or kind == "identity":
            label_chip = _identity_chips(g)
            color = "var(--c-identity)"
        else:
            lbl = g.get("label")
            label_chip = (
                f'<span class="chip {_label_class(lbl)}">{html.escape(_label_text(lbl))}</span>'
            )
            color = _chip_color(lbl)

        body_bits: List[str] = []
        reasoning = g.get("reasoning")
        if reasoning:
            body_bits.append(
                f'<p class="reasoning">{html.escape(reasoning)}</p>'
            )
        if g.get("kind") == "identity" or kind == "identity":
            body_bits.append(_identity_claims_html(g))
        quotes = g.get("quotes") or []
        if quotes:
            qs = "".join(
                f'<blockquote>{html.escape(q)}</blockquote>' for q in quotes
            )
            body_bits.append(f'<div class="quotes">{qs}</div>')

        jump_btn = (
            f'<span class="jump">jump to text &rarr;</span>' if jump_id else ""
        )
        cards_html.append(
            f'''<article class="card" data-jump="{jump_id}" data-spans="{" ".join(my_spans)}"
                 data-color="{color}" onclick="fromCard(this)">
                  <header class="card-head">
                    <span class="model">{html.escape(g.get("model_name", ""))}</span>
                    {label_chip}
                  </header>
                  {"".join(body_bits)}
                  {jump_btn}
                </article>'''
        )

    year_str = html.escape(str(year)) if year is not None else ""
    doc = _DOC_TEMPLATE.format(
        source=html.escape(source),
        year=year_str,
        heading=html.escape(heading),
        aggregate=aggregate_html,
        ticks="".join(ticks),
        speech=speech_html,
        cards="".join(cards_html),
        height=height_px,
    )
    return doc


def _chip_color(label: Optional[str]) -> str:
    return {
        "confrontation": "var(--c-confrontation)",
        "competition": "var(--c-competition)",
        "cooperation": "var(--c-cooperation)",
        "indifference": "var(--c-indifference)",
    }.get(label, "var(--c-none)")


def _identity_chips(g: Dict[str, Any]) -> str:
    n = len(g.get("claims") or [])
    return f'<span class="chip lbl-identity">{n} claim{"s" if n != 1 else ""}</span>'


def _identity_claims_html(g: Dict[str, Any]) -> str:
    rows = []
    for c in g.get("claims") or []:
        others = "".join(
            f'<li>{html.escape(so.get("name",""))} '
            f'<em>({html.escape(so.get("other_type",""))}, {html.escape(so.get("relation",""))})</em></li>'
            for so in (c.get("significant_others") or [])
        )
        others_html = f'<ul class="others">{others}</ul>' if others else ""
        rows.append(
            f'''<div class="claim">
                  <span class="claim-label">{html.escape(c.get("identity_label",""))}</span>
                  <span class="claim-meta">{html.escape(str(c.get("valence","")))} · {html.escape(str(c.get("orientation","")))}</span>
                  {others_html}
                </div>'''
        )
    return f'<div class="claims">{"".join(rows)}</div>'


_DOC_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --c-confrontation:#c0392b; --c-competition:#b8791f;
  --c-cooperation:#1f8a70;   --c-indifference:#6b7280;
  --c-identity:#6d4bd0;       --c-none:#9aa0a8;
  --ink:#20242e; --ink-soft:#565d6a; --blue:#2f5fd0;
  --paper:#faf9f6; --line:#e2ded5; --shell:#1c1f27;
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; }}
body {{
  font-family:'IBM Plex Sans',system-ui,sans-serif;
  color:var(--ink); background:var(--shell);
  -webkit-font-smoothing:antialiased;
}}
.stage {{
  display:grid; grid-template-columns: 1.35fr 1fr;
  gap:0; height:{height}px; background:var(--shell);
  border-radius:10px; overflow:hidden;
  box-shadow:0 1px 0 rgba(255,255,255,.04) inset;
}}

/* ---------- reading column ---------- */
.reading {{
  position:relative; overflow-y:auto; background:var(--paper);
  padding:34px 40px 60px 40px;
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
.mention {{
  cursor:pointer; padding:0 1px; border-radius:2px;
  border-bottom:2px solid var(--c-none); transition:background .2s;
  --pulse:var(--blue);
}}
.mention.lbl-confrontation {{ border-color:var(--c-confrontation); background:rgba(192,57,43,.07); }}
.mention.lbl-competition   {{ border-color:var(--c-competition);  background:rgba(184,121,31,.08); }}
.mention.lbl-cooperation   {{ border-color:var(--c-cooperation);  background:rgba(31,138,112,.08); }}
.mention.lbl-indifference  {{ border-color:var(--c-indifference); background:rgba(107,114,128,.08); }}
.mention.lbl-none          {{ border-color:var(--c-none);         background:rgba(154,160,168,.10); }}
.mention:hover {{ filter:brightness(.97); }}
.quote {{
  background:linear-gradient(transparent 62%, rgba(233,196,79,.55) 62%);
  padding:0 1px;
}}
@keyframes pulse {{
  0%   {{ box-shadow:0 0 0 0 var(--pulse); background:color-mix(in srgb,var(--pulse) 26%,transparent); }}
  100% {{ box-shadow:0 0 0 10px transparent; }}
}}
.pulsing {{ animation:pulse 1.1s ease-out; }}

/* ---------- assessment column ---------- */
.assess {{
  overflow-y:auto; background:var(--shell); color:#e8e6e1;
  padding:30px 26px 60px 26px; border-left:1px solid #000;
}}
.assess::-webkit-scrollbar {{ width:11px; }}
.assess::-webkit-scrollbar-thumb {{ background:#3a3e49; border-radius:6px; border:3px solid var(--shell); }}
.assess-head {{
  font-family:'IBM Plex Mono',monospace; font-size:11px; letter-spacing:.16em;
  text-transform:uppercase; color:#8b93a1; margin:0 0 16px 0;
}}
.agg {{
  background:#23273140; border:1px solid #333846; border-radius:8px;
  padding:12px 14px; margin-bottom:20px; font-size:13px; line-height:1.5; color:#c3c8d2;
}}
.agg b {{ color:#f0f1f4; }}
.agg .agg-run {{ font-family:'IBM Plex Mono',monospace; font-size:11px; color:#8b93a1; text-transform:uppercase; letter-spacing:.08em; }}
.card {{
  background:#22262f; border:1px solid #313746; border-radius:9px;
  padding:15px 16px; margin-bottom:14px; cursor:pointer;
  transition:border-color .18s, transform .18s, box-shadow .18s;
}}
.card:hover {{ border-color:var(--blue); transform:translateY(-1px); box-shadow:0 6px 18px rgba(0,0,0,.35); }}
.card.active {{ border-color:var(--blue); box-shadow:0 0 0 1px var(--blue); }}
.card-head {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:9px; }}
.model {{ font-family:'IBM Plex Mono',monospace; font-size:11.5px; color:#9aa2b0; letter-spacing:.02em; }}
.chip {{
  font-size:11px; font-weight:600; letter-spacing:.03em; text-transform:uppercase;
  padding:3px 9px; border-radius:20px; color:#fff; white-space:nowrap;
}}
.chip.lbl-confrontation {{ background:var(--c-confrontation); }}
.chip.lbl-competition   {{ background:var(--c-competition); }}
.chip.lbl-cooperation   {{ background:var(--c-cooperation); }}
.chip.lbl-indifference  {{ background:var(--c-indifference); }}
.chip.lbl-identity      {{ background:var(--c-identity); }}
.chip.lbl-none          {{ background:var(--c-none); }}
.reasoning {{ font-size:13.5px; line-height:1.55; color:#c7ccd6; margin:0 0 10px 0; }}
.quotes blockquote {{
  margin:6px 0; padding:5px 11px; border-left:3px solid #e9c44f;
  background:#2a2e38; font-family:'Newsreader',serif; font-size:14px;
  font-style:italic; color:#dfe2e8; border-radius:0 4px 4px 0;
}}
.claims {{ margin:2px 0 8px 0; }}
.claim {{ padding:7px 0; border-top:1px dashed #363c4a; }}
.claim:first-child {{ border-top:none; }}
.claim-label {{ font-weight:600; color:#efe7ff; font-size:13.5px; }}
.claim-meta {{ font-family:'IBM Plex Mono',monospace; font-size:11px; color:#9aa2b0; margin-left:8px; }}
.others {{ margin:5px 0 0 0; padding-left:16px; font-size:12px; color:#a9b0bd; }}
.others em {{ color:#828a98; font-style:normal; }}
.jump {{
  display:inline-block; margin-top:4px; font-size:11.5px; font-weight:600;
  color:var(--blue); letter-spacing:.02em;
}}
.card:hover .jump {{ text-decoration:underline; }}
</style></head>
<body>
<div class="stage">
  <section class="reading" id="reading">
    <div class="rail">{ticks}</div>
    <div class="doc-head">
      <div class="code">{source} · {year}</div>
      <h1>{heading}</h1>
    </div>
    <div class="speech">{speech}</div>
  </section>
  <section class="assess" id="assess">
    <div class="assess-head">Machine assessment</div>
    {aggregate}
    {cards}
  </section>
</div>
<script>
  const reading = document.getElementById('reading');
  function pulse(ids, color) {{
    (ids||'').split(' ').filter(Boolean).forEach(function(id) {{
      const e = document.getElementById(id); if (!e) return;
      if (color) e.style.setProperty('--pulse', color);
      e.classList.remove('pulsing'); void e.offsetWidth; e.classList.add('pulsing');
    }});
  }}
  function jump(id, color) {{
    const e = document.getElementById(id); if (!e) return;
    e.scrollIntoView({{behavior:'smooth', block:'center'}});
    pulse(id, color);
  }}
  function fromCard(card) {{
    document.querySelectorAll('.card.active').forEach(c => c.classList.remove('active'));
    card.classList.add('active');
    const jid = card.dataset.jump;
    if (jid) jump(jid, card.dataset.color);
    pulse(card.dataset.spans, card.dataset.color);
  }}
  function fromText(span) {{
    const target = [...document.querySelectorAll('.card')].find(c => c.dataset.spans.split(' ').includes(span.id));
    if (target) {{
      document.querySelectorAll('.card.active').forEach(c => c.classList.remove('active'));
      target.classList.add('active');
      target.scrollIntoView({{behavior:'smooth', block:'center'}});
      pulse(span.id, target.dataset.color);
    }}
  }}
</script>
</body></html>"""
