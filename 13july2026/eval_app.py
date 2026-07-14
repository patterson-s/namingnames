#!/usr/bin/env python3

import json
import html as _html

import streamlit as st
import streamlit.components.v1 as components

from neon_db import get_conn
from eval_queries import (
    list_evaluation_runs,
    load_sample_doc_ids,
    get_speech,
    get_targets_for_doc,
    get_four_point_rows,
    get_identity_rows,
    get_four_point_aggregates,
    get_identity_aggregates,
    get_annotated_keys,
    save_annotation,
    progress_for_annotator,
    progress_all_annotators,
    speech_progress,
)
from highlight import find_surface_form_spans, find_quote_span
from review_render import assemble_spans, build_reading_html, _label_class

FOUR_POINT_LABELS = ["confrontation", "competition", "cooperation", "indifference"]


def render_html_iframe(doc: str, height: int) -> None:
    """Embed a self-contained HTML document (with its own JS) in a sandboxed
    iframe. `st.iframe` is the supported API on newer Streamlit; the deprecated
    `st.components.v1.html` (removed after 2026-06-01) is the fallback for older
    versions that predate `st.iframe`."""
    if hasattr(st, "iframe"):
        st.iframe(doc, height=height)
    else:
        components.html(doc, height=height, scrolling=False)


st.set_page_config(page_title="Naming Names — Annotation Console", layout="wide")

# ---------------------------------------------------------------- global chrome
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
    html, body, [class*="css"], .stApp { font-family:'IBM Plex Sans',system-ui,sans-serif; }
    .block-container { padding-top:1.6rem; padding-bottom:3rem; max-width:1400px; }
    h1, h2, h3 { font-family:'Newsreader',serif !important; letter-spacing:-.01em; }
    .masthead { display:flex; align-items:baseline; gap:.7rem; border-bottom:2px solid #20242e;
                padding-bottom:.5rem; margin-bottom:.2rem; }
    .masthead .brand { font-family:'Newsreader',serif; font-size:1.55rem; font-weight:600; color:#20242e; }
    .masthead .sub { font-family:'IBM Plex Mono',monospace; font-size:.7rem; letter-spacing:.16em;
                     text-transform:uppercase; color:#8a8577; }
    .entry-meta { font-family:'IBM Plex Mono',monospace; font-size:.72rem; letter-spacing:.08em;
                  text-transform:uppercase; color:#6b7280; }
    .review-title { font-family:'Newsreader',serif; font-size:1.15rem; font-weight:500; margin:.2rem 0 .1rem 0; }
    div[data-testid="stExpander"] { border:1px solid #ddd8cd; border-radius:8px; background:#f6f4ef; }
    .assess-title { font-family:'IBM Plex Mono',monospace; font-size:.72rem; letter-spacing:.16em;
                    text-transform:uppercase; color:#8a8577; margin:.1rem 0 .55rem 0; }
    .lbl-pill { display:inline-block; font-size:.68rem; font-weight:600; text-transform:uppercase;
                letter-spacing:.03em; color:#fff; padding:2px 8px; border-radius:20px; }
    .lbl-confrontation{background:#c0392b;} .lbl-competition{background:#b8791f;}
    .lbl-cooperation{background:#1f8a70;} .lbl-indifference{background:#6b7280;}
    .lbl-identity{background:#6d4bd0;} .lbl-none{background:#9aa0a8;}
    .agg { background:#f6f4ef; border:1px solid #ddd8cd; border-radius:8px; padding:10px 12px;
           margin-bottom:12px; font-size:.8rem; line-height:1.5; color:#3a3f4a; }
    .agg b { color:#20242e; }
    .agg-run { font-family:'IBM Plex Mono',monospace; font-size:.66rem; color:#8a8577;
               text-transform:uppercase; letter-spacing:.08em; display:block; margin-bottom:3px; }
    .stButton>button { border-radius:7px; font-weight:600; }
    /* Pin the reading pane so it stays at eye level while the assessment
       column scrolls beside it. Scoped to the one row holding the iframe.
       Matches both the old ("column") and new ("stColumn") Streamlit test-ids. */
    div[data-testid="stHorizontalBlock"]:has(iframe) > div[data-testid="column"]:first-child,
    div[data-testid="stHorizontalBlock"]:has(iframe) > div[data-testid="stColumn"]:first-child {
        position:sticky; top:0.75rem; align-self:flex-start; z-index:3;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- aggregate html
def four_point_aggregate_html(conn, doc_id: str, target: str) -> str:
    rows = get_four_point_aggregates(conn, doc_id, target)
    if not rows:
        return ""
    by_run: dict[str, dict] = {}
    for r in rows:
        by_run.setdefault(r["base_run_id"], {})[r["method"]] = r

    blocks = []
    for base_run_id, methods in by_run.items():
        parts = [f'<span class="agg-run">{_html.escape(base_run_id)}</span>']
        det = methods.get("deterministic")
        if det:
            counts = det["label_counts"] or {}
            counts_str = ", ".join(f"{k}: {v}" for k, v in counts.items()) or "—"
            tie = " · tie" if det["is_tie"] else ""
            lbl = det["aggregate_label"] or "—"
            chip = f'<span class="lbl-pill {_label_class(det["aggregate_label"])}">{_html.escape(str(lbl))}</span>'
            parts.append(
                f'<div>majority {chip}{tie}<br><span style="opacity:.7">n={det["n_chunks"]} · {_html.escape(counts_str)}</span></div>'
            )
        llm = methods.get("llm")
        if llm:
            lbl = llm["aggregate_label"] or "(malformed)"
            chip = f'<span class="lbl-pill {_label_class(llm["aggregate_label"])}">{_html.escape(str(lbl))}</span>'
            parts.append(f'<div>llm consolidated {chip}</div>')
        blocks.append(f'<div class="agg">{"".join(parts)}</div>')
    return "".join(blocks)


def identity_aggregate_html(conn, doc_id: str) -> str:
    rows = get_identity_aggregates(conn, doc_id)
    if not rows:
        return ""
    by_run: dict[str, dict] = {}
    for r in rows:
        by_run.setdefault(r["base_run_id"], {})[r["method"]] = r

    blocks = []
    for base_run_id, methods in by_run.items():
        parts = [f'<span class="agg-run">{_html.escape(base_run_id)}</span>']
        det = methods.get("deterministic")
        if det:
            vc = det["valence_counts"] or {}
            vc_str = ", ".join(f"{k}: {v}" for k, v in vc.items()) or "—"
            labels = det["distinct_identity_labels"] or []
            parts.append(
                f'<div><b>{det["n_claims"]}</b> claim(s) across {det["n_chunks"]} excerpt(s)'
                f'<br><span style="opacity:.7">valence {_html.escape(vc_str)}</span></div>'
            )
            if labels:
                parts.append(
                    '<div style="opacity:.7">' + _html.escape(", ".join(labels)) + "</div>"
                )
        llm = methods.get("llm")
        if llm:
            claims = llm["consolidated_claims"] or []
            parts.append(f'<div>llm consolidated <b>{len(claims)}</b> distinct claim(s)</div>')
        blocks.append(f'<div class="agg">{"".join(parts)}</div>')
    return "".join(blocks)


# ---------------------------------------------------------------- entries / resume
@st.cache_data(show_spinner="Loading evaluation run…")
def cached_doc_ids(run_file: str):
    return load_sample_doc_ids(run_file)


def build_entries(_conn, doc_ids):
    entries = []
    for doc_id in doc_ids:
        for t in get_targets_for_doc(_conn, doc_id):
            entries.append({"doc_id": doc_id, **t})
    return entries


def entry_row_keys(conn, entry) -> tuple[str, list[int]]:
    table = "identity_classifications" if entry["is_self"] else "four_point_classifications"
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id FROM {table} WHERE doc_id = %s AND target = %s",
            (entry["doc_id"], entry["target"]),
        )
        ids = [r["id"] for r in cur.fetchall()]
    return table, ids


def find_resume_index(conn, entries, done_keys) -> int:
    for i, entry in enumerate(entries):
        table, ids = entry_row_keys(conn, entry)
        keys = {(table, rid) for rid in ids}
        if not keys.issubset(done_keys):
            return i
    return max(len(entries) - 1, 0)


def build_speech_index(conn, entries):
    """Ordered, de-duplicated speech list for the jump picker. Order = first
    appearance in entries; first_idx = index of the speech's first entry."""
    with conn.cursor() as cur:
        cur.execute("SELECT iso3, name FROM countries")
        names = {r["iso3"]: r["name"] for r in cur.fetchall()}

    speeches = []
    by_doc = {}
    for i, entry in enumerate(entries):
        doc_id = entry["doc_id"]
        if doc_id not in by_doc:
            speech = get_speech(conn, doc_id)
            rec = {
                "doc_id": doc_id,
                "source_name": names.get(speech["source"], speech["source"]),
                "year": speech["year"],
                "first_idx": i,
                "n_targets": 0,
            }
            by_doc[doc_id] = rec
            speeches.append(rec)
        by_doc[doc_id]["n_targets"] += 1
    return speeches


def start_run(run_file: str):
    with get_conn() as conn:
        doc_ids = cached_doc_ids(run_file)
        entries = build_entries(conn, doc_ids)
        done_keys = get_annotated_keys(conn, st.session_state.annotator_name)
        resume_idx = find_resume_index(conn, entries, done_keys)
        speeches = build_speech_index(conn, entries)
    st.session_state.run_file = run_file
    st.session_state.entries = entries
    st.session_state.speeches = speeches
    st.session_state.entry_idx = resume_idx
    st.session_state.focus_span = None


# ---------------------------------------------------------------- screens
def name_entry_screen():
    st.markdown(
        '<div class="masthead"><span class="brand">Naming Names</span>'
        '<span class="sub">annotation console</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("Read the primary source. Countersign or correct the machine's read.")

    with get_conn() as conn:
        overall = progress_all_annotators(conn)
    total = overall["total"]
    if overall["annotators"] and total:
        st.markdown('<div class="assess-title">Progress by evaluator</div>', unsafe_allow_html=True)
        for a in overall["annotators"]:
            done = a["done"]
            st.progress(min(done / total, 1.0), text=f"{a['name']} — {done} / {total}")
    else:
        st.caption("No annotations recorded yet.")

    runs = list_evaluation_runs()
    name = st.text_input("Your name")
    if runs:
        labels = [r["label"] for r in runs]
        choice = st.selectbox("Evaluation run", labels, index=0)
        run_file = runs[labels.index(choice)]["file"]
    else:
        st.warning("No evaluation runs found in data/ (expected `sample_*.json`).")
        run_file = None

    if st.button("Start / Resume session", type="primary", disabled=not (name.strip() and run_file)):
        st.session_state.annotator_name = name.strip()
        start_run(run_file)
        st.rerun()


def render_four_point(conn, entry, entry_idx):
    doc_id, target = entry["doc_id"], entry["target"]
    speech = get_speech(conn, doc_id)
    rows = get_four_point_rows(conn, doc_id, target)

    groups = []
    for row in rows:
        forms = [f.strip() for f in (row["gpe_entity"] or "").split(",")]
        tspans = find_surface_form_spans(speech["text"], row["chunk_start"], row["chunk_text"], forms)
        qspans = []
        for q in (row["evidence_quotes"] or []):
            sp = find_quote_span(row["chunk_text"], row["chunk_start"], q)
            if sp:
                qspans.append(sp)
        cs = row["chunk_start"]
        chunk_span = (cs, min(cs + len(row["chunk_text"]), len(speech["text"])))
        groups.append(
            {
                "card_id": f"c{row['id']}",
                "model_name": row["model_name"],
                "kind": "four_point",
                "label": row["label"],
                "reasoning": row["reasoning"],
                "quotes": row["evidence_quotes"] or [],
                "target_spans": tspans,
                "quote_spans": qspans,
                "chunk_span": chunk_span,
                "malformed": row["malformed"],
            }
        )

    st.markdown(
        f'<div class="review-title">Posture toward {_html.escape(entry["target_name"])}</div>',
        unsafe_allow_html=True,
    )
    assembled = assemble_spans(speech["text"], groups)
    card_jump = assembled["card_jump"]

    col_read, col_assess = st.columns([1.35, 1], gap="medium")
    with col_read:
        render_html_iframe(
            build_reading_html(
                source=speech["source"],
                year=speech["year"],
                heading=f"Posture toward {entry['target_name']}",
                speech_html=assembled["speech_html"],
                ticks_html=assembled["ticks_html"],
                focus_span_id=st.session_state.get("focus_span"),
            ),
            800,
        )

    save_payloads = []
    with col_assess:
        st.markdown('<div class="assess-title">Machine assessment</div>', unsafe_allow_html=True)
        agg = four_point_aggregate_html(conn, doc_id, target)
        if agg:
            st.markdown(agg, unsafe_allow_html=True)

        for row in rows:
            cid = f"c{row['id']}"
            key_prefix = f"fp_{entry_idx}_{row['id']}"
            edited = (
                st.session_state.get(f"{key_prefix}_label", row["label"]) != row["label"]
                or st.session_state.get(f"{key_prefix}_flag", False)
            )
            header = f"{row['model_name']} — {row['label'] or 'malformed'}" + ("  ✎" if edited else "")
            with st.expander(header, expanded=False):
                pill = f'<span class="lbl-pill {_label_class(row["label"])}">{row["label"] or "malformed"}</span>'
                st.markdown(f"Model label: {pill}", unsafe_allow_html=True)
                if row["reasoning"]:
                    st.markdown(f"**Reasoning.** {row['reasoning']}")
                for q in (row["evidence_quotes"] or []):
                    st.markdown(f"> {q}")

                if card_jump.get(cid):
                    if st.button("Jump to text →", key=f"jump_{key_prefix}"):
                        st.session_state.focus_span = card_jump[cid]
                        st.rerun()

                options = FOUR_POINT_LABELS
                default_idx = options.index(row["label"]) if row["label"] in options else 0
                c1, c2 = st.columns([2, 1])
                with c1:
                    corrected_label = st.selectbox(
                        "Correct label", options, index=default_idx, key=f"{key_prefix}_label"
                    )
                with c2:
                    flagged = st.checkbox("Flag as mistake", key=f"{key_prefix}_flag")
                feedback = st.text_area("Feedback", key=f"{key_prefix}_feedback", height=70)

                original_data = {
                    "label": row["label"],
                    "ambiguous": row["ambiguous"],
                    "reasoning": row["reasoning"],
                    "evidence_quotes": row["evidence_quotes"],
                }
                corrected_data = None if corrected_label == row["label"] else {"label": corrected_label}
                save_payloads.append(
                    dict(
                        scheme="four_point",
                        target_table="four_point_classifications",
                        target_id=row["id"],
                        doc_id=doc_id,
                        chunk_id=row["chunk_id"],
                        source=row["source"],
                        target=row["target"],
                        run_id=row["run_id"],
                        original_data=original_data,
                        corrected_data=corrected_data,
                        is_flagged_mistake=flagged,
                        feedback_text=feedback or None,
                    )
                )
    return save_payloads


def render_identity(conn, entry, entry_idx):
    doc_id = entry["doc_id"]
    speech = get_speech(conn, doc_id)
    source = speech["source"]
    classifications = get_identity_rows(conn, doc_id)

    groups = []
    for classification in classifications:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT gpe_entity FROM entity_mentions "
                "WHERE chunk_id = %s AND source = %s AND target = %s",
                (classification["chunk_id"], source, source),
            )
            forms = [r["gpe_entity"] for r in cur.fetchall() if r["gpe_entity"]]
        tspans = find_surface_form_spans(
            speech["text"], classification["chunk_start"], classification["chunk_text"], forms
        )
        quotes_flat = []
        qspans = []
        claims_norm = []
        for c in classification["claims"]:
            for q in (c["evidence_quotes"] or []):
                quotes_flat.append(q)
                sp = find_quote_span(classification["chunk_text"], classification["chunk_start"], q)
                if sp:
                    qspans.append(sp)
            claims_norm.append(
                {
                    "identity_label": c["identity_label"],
                    "valence": c["valence"],
                    "orientation": c["orientation"],
                    "significant_others": [
                        {"name": so["name"], "other_type": so["other_type"], "relation": so["relation"]}
                        for so in c["significant_others"]
                    ],
                }
            )
        cs = classification["chunk_start"]
        chunk_span = (cs, min(cs + len(classification["chunk_text"]), len(speech["text"])))
        groups.append(
            {
                "card_id": f"i{classification['id']}",
                "model_name": classification["model_name"],
                "kind": "identity",
                "label": None,
                "reasoning": classification["reasoning"],
                "quotes": quotes_flat,
                "target_spans": tspans,
                "quote_spans": qspans,
                "chunk_span": chunk_span,
                "claims": claims_norm,
            }
        )

    st.markdown('<div class="review-title">National self-identity</div>', unsafe_allow_html=True)
    assembled = assemble_spans(speech["text"], groups)
    card_jump = assembled["card_jump"]

    col_read, col_assess = st.columns([1.35, 1], gap="medium")
    with col_read:
        render_html_iframe(
            build_reading_html(
                source=source,
                year=speech["year"],
                heading="National self-identity",
                speech_html=assembled["speech_html"],
                ticks_html=assembled["ticks_html"],
                focus_span_id=st.session_state.get("focus_span"),
            ),
            800,
        )

    save_payloads = []
    with col_assess:
        st.markdown('<div class="assess-title">Machine assessment</div>', unsafe_allow_html=True)
        agg = identity_aggregate_html(conn, doc_id)
        if agg:
            st.markdown(agg, unsafe_allow_html=True)

        for classification in classifications:
            cid = f"i{classification['id']}"
            claims_summary = json.dumps(
                {
                    "reasoning": classification["reasoning"],
                    "claims": [
                        {
                            "identity_label": c["identity_label"],
                            "valence": c["valence"],
                            "orientation": c["orientation"],
                            "evidence_quotes": c["evidence_quotes"],
                            "significant_others": [
                                {"name": so["name"], "other_type": so["other_type"], "relation": so["relation"]}
                                for so in c["significant_others"]
                            ],
                        }
                        for c in classification["claims"]
                    ],
                },
                indent=2,
            )
            key_prefix = f"id_{entry_idx}_{classification['id']}"
            edited = bool(st.session_state.get(f"{key_prefix}_flag", False))
            n_claims = len(classification["claims"])
            header = (
                f"{classification['model_name']} — {n_claims} claim(s)" + ("  ✎" if edited else "")
            )
            with st.expander(header, expanded=False):
                st.markdown(
                    f'<span class="lbl-pill lbl-identity">{n_claims} claim(s)</span>',
                    unsafe_allow_html=True,
                )
                if classification["reasoning"]:
                    st.markdown(f"**Reasoning.** {classification['reasoning']}")
                for c in classification["claims"]:
                    line = f"- **{c['identity_label']}** — {c['valence']} · {c['orientation']}"
                    st.markdown(line)
                    for so in c["significant_others"]:
                        st.markdown(
                            f"    - {so['name']} _({so['other_type']}, {so['relation']})_"
                        )

                if card_jump.get(cid):
                    if st.button("Jump to text →", key=f"jump_{key_prefix}"):
                        st.session_state.focus_span = card_jump[cid]
                        st.rerun()

                corrected_json_text = st.text_area(
                    "Corrected claims (JSON, optional — edit to correct)",
                    value=claims_summary,
                    height=200,
                    key=f"{key_prefix}_json",
                )
                flagged = st.checkbox("Flag as mistake", key=f"{key_prefix}_flag")
                feedback = st.text_area("Feedback", key=f"{key_prefix}_feedback", height=70)

                original_data = {
                    "reasoning": classification["reasoning"],
                    "claims": [
                        {
                            "identity_label": c["identity_label"],
                            "valence": c["valence"],
                            "orientation": c["orientation"],
                            "evidence_quotes": c["evidence_quotes"],
                            "significant_others": [dict(so) for so in c["significant_others"]],
                        }
                        for c in classification["claims"]
                    ],
                }
                corrected_data = None
                try:
                    parsed = json.loads(corrected_json_text)
                    if parsed != json.loads(claims_summary):
                        corrected_data = parsed
                except json.JSONDecodeError:
                    st.warning("Corrected claims JSON is invalid — will not be saved until fixed.")

                save_payloads.append(
                    dict(
                        scheme="identity",
                        target_table="identity_classifications",
                        target_id=classification["id"],
                        doc_id=doc_id,
                        chunk_id=classification["chunk_id"],
                        source=classification["source"],
                        target=classification["target"],
                        run_id=classification["run_id"],
                        original_data=original_data,
                        corrected_data=corrected_data,
                        is_flagged_mistake=flagged,
                        feedback_text=feedback or None,
                    )
                )
    return save_payloads


def run_switcher():
    runs = list_evaluation_runs()
    if not runs:
        return
    files = [r["file"] for r in runs]
    labels = {r["file"]: r["label"] for r in runs}
    current = st.session_state.get("run_file", files[0])
    idx = files.index(current) if current in files else 0
    with st.sidebar:
        st.markdown(f"**Annotator**  \n{st.session_state.annotator_name}")
        choice = st.selectbox(
            "Evaluation run", files, index=idx, format_func=lambda f: labels[f]
        )
        if choice != current:
            start_run(choice)
            st.rerun()


def speech_picker(conn):
    """Sidebar selector to jump directly to any speech's first entry."""
    speeches = st.session_state.get("speeches") or []
    if not speeches:
        return
    entries = st.session_state.entries
    entry_idx = st.session_state.entry_idx
    current_doc = entries[entry_idx]["doc_id"] if entry_idx < len(entries) else None

    doc_ids = [s["doc_id"] for s in speeches]
    prog = speech_progress(conn, st.session_state.annotator_name, doc_ids)

    def _label(i: int) -> str:
        s = speeches[i]
        p = prog.get(s["doc_id"], {})
        mark = "✓ " if p.get("total") and p["done"] >= p["total"] else ""
        return f'{mark}{s["source_name"]} {s["year"]} · {s["n_targets"]} target(s)'

    current_pos = next(
        (i for i, s in enumerate(speeches) if s["doc_id"] == current_doc), 0
    )
    with st.sidebar:
        choice = st.selectbox(
            "Jump to speech",
            range(len(speeches)),
            index=current_pos,
            format_func=_label,
        )
    if current_doc is not None and speeches[choice]["doc_id"] != current_doc:
        st.session_state.entry_idx = speeches[choice]["first_idx"]
        st.session_state.focus_span = None
        st.rerun()


def main_screen():
    run_switcher()
    entries = st.session_state.entries
    entry_idx = st.session_state.entry_idx

    st.markdown(
        '<div class="masthead"><span class="brand">Naming Names</span>'
        '<span class="sub">annotation console</span></div>',
        unsafe_allow_html=True,
    )

    with get_conn() as conn:
        speech_picker(conn)
        entry_idx = st.session_state.entry_idx

        progress = progress_for_annotator(conn, st.session_state.annotator_name)
        st.progress(progress["fraction"], text=f"{progress['done']} / {progress['total']} rows annotated")

        if entry_idx >= len(entries):
            st.success("All entries in this evaluation run have been reviewed. Thank you!")
            return

        entry = entries[entry_idx]
        st.markdown(
            f'<div class="entry-meta">Entry {entry_idx + 1} of {len(entries)} · '
            f'{_html.escape(entry["doc_id"])}</div>',
            unsafe_allow_html=True,
        )

        if entry["is_self"]:
            save_payloads = render_identity(conn, entry, entry_idx)
        else:
            save_payloads = render_four_point(conn, entry, entry_idx)

        col_prev, col_next, col_save, _ = st.columns([1, 1, 1, 2])
        with col_prev:
            if st.button("← Previous", disabled=(entry_idx == 0)):
                st.session_state.entry_idx -= 1
                st.session_state.focus_span = None
                st.rerun()
        with col_next:
            if st.button("Next →", disabled=(entry_idx >= len(entries) - 1)):
                st.session_state.entry_idx += 1
                st.session_state.focus_span = None
                st.rerun()
        with col_save:
            if st.button("Save & Next →", type="primary"):
                for payload in save_payloads:
                    save_annotation(conn, annotator_name=st.session_state.annotator_name, **payload)
                st.session_state.entry_idx += 1
                st.session_state.focus_span = None
                st.rerun()


def main():
    if "annotator_name" not in st.session_state:
        name_entry_screen()
    else:
        main_screen()


if __name__ == "__main__":
    main()
