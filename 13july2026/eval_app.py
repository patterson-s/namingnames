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
)
from highlight import find_surface_form_spans, find_quote_span
from review_render import build_review_html, _label_class

FOUR_POINT_LABELS = ["confrontation", "competition", "cooperation", "indifference"]

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
    .verdict-hd { font-family:'IBM Plex Mono',monospace; font-size:.72rem; letter-spacing:.14em;
                  text-transform:uppercase; color:#2f5fd0; margin:.4rem 0 .3rem 0; }
    .lbl-pill { display:inline-block; font-size:.68rem; font-weight:600; text-transform:uppercase;
                letter-spacing:.03em; color:#fff; padding:2px 8px; border-radius:20px; }
    .lbl-confrontation{background:#c0392b;} .lbl-competition{background:#b8791f;}
    .lbl-cooperation{background:#1f8a70;} .lbl-indifference{background:#6b7280;}
    .lbl-identity{background:#6d4bd0;} .lbl-none{background:#9aa0a8;}
    .stButton>button { border-radius:7px; font-weight:600; }
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
            chip = f'<span class="chip {_label_class(det["aggregate_label"])}">{_html.escape(str(lbl))}</span>'
            parts.append(
                f'<div>majority {chip}{tie}<br><span style="opacity:.7">n={det["n_chunks"]} · {_html.escape(counts_str)}</span></div>'
            )
        llm = methods.get("llm")
        if llm:
            lbl = llm["aggregate_label"] or "(malformed)"
            chip = f'<span class="chip {_label_class(llm["aggregate_label"])}">{_html.escape(str(lbl))}</span>'
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


def start_run(run_file: str):
    with get_conn() as conn:
        doc_ids = cached_doc_ids(run_file)
        entries = build_entries(conn, doc_ids)
        done_keys = get_annotated_keys(conn, st.session_state.annotator_name)
        resume_idx = find_resume_index(conn, entries, done_keys)
    st.session_state.run_file = run_file
    st.session_state.entries = entries
    st.session_state.entry_idx = resume_idx


# ---------------------------------------------------------------- screens
def name_entry_screen():
    st.markdown(
        '<div class="masthead"><span class="brand">Naming Names</span>'
        '<span class="sub">annotation console</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("Read the primary source. Countersign or correct the machine's read.")

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
                "malformed": row["malformed"],
            }
        )

    st.markdown(
        f'<div class="review-title">Posture toward {_html.escape(entry["target_name"])}</div>',
        unsafe_allow_html=True,
    )
    doc = build_review_html(
        source=speech["source"],
        year=speech["year"],
        heading=f"Posture toward {entry['target_name']}",
        kind="four_point",
        speech_text=speech["text"],
        groups=groups,
        aggregate_html=four_point_aggregate_html(conn, doc_id, target),
    )
    components.html(doc, height=780, scrolling=False)

    save_payloads = []
    st.markdown('<div class="verdict-hd">Your review</div>', unsafe_allow_html=True)
    for row in rows:
        pill = f'<span class="lbl-pill {_label_class(row["label"])}">{row["label"] or "malformed"}</span>'
        with st.expander(f"{row['model_name']}", expanded=True):
            st.markdown(f"Model label: {pill}", unsafe_allow_html=True)
            key_prefix = f"fp_{entry_idx}_{row['id']}"
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
                "claims": claims_norm,
            }
        )

    st.markdown('<div class="review-title">National self-identity</div>', unsafe_allow_html=True)
    doc = build_review_html(
        source=source,
        year=speech["year"],
        heading="National self-identity",
        kind="identity",
        speech_text=speech["text"],
        groups=groups,
        aggregate_html=identity_aggregate_html(conn, doc_id),
    )
    components.html(doc, height=780, scrolling=False)

    save_payloads = []
    st.markdown('<div class="verdict-hd">Your review</div>', unsafe_allow_html=True)
    for classification in classifications:
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
        with st.expander(
            f"{classification['model_name']} — {len(classification['claims'])} claim(s)", expanded=True
        ):
            key_prefix = f"id_{entry_idx}_{classification['id']}"
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
                edited = json.loads(corrected_json_text)
                if edited != json.loads(claims_summary):
                    corrected_data = edited
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

        col_prev, col_save, _ = st.columns([1, 1, 3])
        with col_prev:
            if st.button("← Previous", disabled=(entry_idx == 0)):
                st.session_state.entry_idx -= 1
                st.rerun()
        with col_save:
            if st.button("Save & Next →", type="primary"):
                for payload in save_payloads:
                    save_annotation(conn, annotator_name=st.session_state.annotator_name, **payload)
                st.session_state.entry_idx += 1
                st.rerun()


def main():
    if "annotator_name" not in st.session_state:
        name_entry_screen()
    else:
        main_screen()


if __name__ == "__main__":
    main()
