#!/usr/bin/env python3

import json
import streamlit as st

from neon_db import get_conn
from eval_queries import (
    load_sample_doc_ids,
    get_speech,
    get_targets_for_doc,
    get_four_point_rows,
    get_identity_rows,
    get_annotated_keys,
    save_annotation,
    progress_for_annotator,
)
from highlight import find_surface_form_spans, find_quote_span, render_speech_html

FOUR_POINT_LABELS = ["confrontation", "competition", "cooperation", "indifference"]

st.set_page_config(page_title="Naming Names — Annotation", layout="wide")

st.markdown(
    """
    <style>
    .speech-box { max-height: 480px; overflow-y: auto; padding: 1rem; border: 1px solid rgba(128,128,128,0.3);
                  border-radius: 6px; line-height: 1.6; }
    mark.evidence { background-color: #ffe08a; padding: 0 2px; }
    b.target-bold { background-color: #a5d8ff; padding: 0 2px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_self_mention_spans(conn, doc_id: str, source: str):
    query = """
        SELECT em.gpe_entity, c.chunk_start, c.text AS chunk_text
        FROM entity_mentions em
        JOIN chunks c ON c.chunk_id = em.chunk_id
        WHERE em.doc_id = %s AND em.source = %s AND em.target = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id, source, source))
        return cur.fetchall()


@st.cache_data(show_spinner="Loading pilot sample...")
def cached_doc_ids():
    return load_sample_doc_ids()


def build_entries(_conn, doc_ids):
    entries = []
    for doc_id in doc_ids:
        for t in get_targets_for_doc(_conn, doc_id):
            entries.append({"doc_id": doc_id, **t})
    return entries


def entry_row_keys(conn, entry) -> tuple[str, list[int]]:
    if entry["is_self"]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM identity_classifications WHERE doc_id = %s AND target = %s",
                (entry["doc_id"], entry["target"]),
            )
            ids = [r["id"] for r in cur.fetchall()]
        return "identity_classifications", ids
    else:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM four_point_classifications WHERE doc_id = %s AND target = %s",
                (entry["doc_id"], entry["target"]),
            )
            ids = [r["id"] for r in cur.fetchall()]
        return "four_point_classifications", ids


def find_resume_index(conn, entries, done_keys) -> int:
    for i, entry in enumerate(entries):
        table, ids = entry_row_keys(conn, entry)
        keys = {(table, rid) for rid in ids}
        if not keys.issubset(done_keys):
            return i
    return max(len(entries) - 1, 0)


def name_entry_screen():
    st.title("Naming Names — Annotation")
    name = st.text_input("Your name")
    if st.button("Start / Resume session", disabled=not name.strip()):
        st.session_state.annotator_name = name.strip()
        with get_conn() as conn:
            doc_ids = cached_doc_ids()
            entries = build_entries(conn, doc_ids)
            done_keys = get_annotated_keys(conn, st.session_state.annotator_name)
            resume_idx = find_resume_index(conn, entries, done_keys)
        st.session_state.entries = entries
        st.session_state.entry_idx = resume_idx
        st.rerun()


def render_four_point(conn, entry, entry_idx):
    doc_id, target = entry["doc_id"], entry["target"]
    speech = get_speech(conn, doc_id)
    rows = get_four_point_rows(conn, doc_id, target)

    target_spans = []
    quote_spans = []
    for row in rows:
        forms = [f.strip() for f in (row["gpe_entity"] or "").split(",")]
        target_spans.extend(find_surface_form_spans(speech["text"], row["chunk_start"], row["chunk_text"], forms))
        for quote in (row["evidence_quotes"] or []):
            span = find_quote_span(row["chunk_text"], row["chunk_start"], quote)
            if span:
                quote_spans.append(span)

    col_main, col_side = st.columns([2, 1])
    with col_main:
        st.subheader(f"{speech['source']} ({speech['year']}) -> {entry['target_name']}")
        html_text = render_speech_html(speech["text"], target_spans, quote_spans)
        st.markdown(f'<div class="speech-box">{html_text}</div>', unsafe_allow_html=True)

    with col_side:
        st.subheader("Four-point classifications")
        save_payloads = []
        for row in rows:
            with st.expander(f"{row['model_name']} — {row['label'] or '(malformed)'}", expanded=True):
                st.write("**Reasoning:**", row["reasoning"] or "_none_")
                st.write("**Evidence quotes:**")
                for q in (row["evidence_quotes"] or []):
                    st.markdown(f"> {q}")

                key_prefix = f"fp_{entry_idx}_{row['id']}"
                options = FOUR_POINT_LABELS
                default_idx = options.index(row["label"]) if row["label"] in options else 0
                corrected_label = st.selectbox("Correct label", options, index=default_idx, key=f"{key_prefix}_label")
                flagged = st.checkbox("Flag as mistake", key=f"{key_prefix}_flag")
                feedback = st.text_area("Feedback", key=f"{key_prefix}_feedback")

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
    classifications = get_identity_rows(conn, doc_id)

    self_rows = get_self_mention_spans(conn, doc_id, speech["source"])
    target_spans = []
    quote_spans = []
    for row in self_rows:
        forms = [row["gpe_entity"]] if row["gpe_entity"] else []
        target_spans.extend(find_surface_form_spans(speech["text"], row["chunk_start"], row["chunk_text"], forms))
    for classification in classifications:
        for claim in classification["claims"]:
            for quote in (claim["evidence_quotes"] or []):
                span = find_quote_span(classification["chunk_text"], classification["chunk_start"], quote)
                if span:
                    quote_spans.append(span)

    col_main, col_side = st.columns([2, 1])
    with col_main:
        st.subheader(f"{speech['source']} ({speech['year']}) -> self-identity")
        html_text = render_speech_html(speech["text"], target_spans, quote_spans)
        st.markdown(f'<div class="speech-box">{html_text}</div>', unsafe_allow_html=True)

    with col_side:
        st.subheader("Identity classifications")
        save_payloads = []
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
                st.write("**Reasoning:**", classification["reasoning"] or "_none_")
                for c in classification["claims"]:
                    st.markdown(f"- **{c['identity_label']}** ({c['valence']}, {c['orientation']})")
                    for so in c["significant_others"]:
                        st.markdown(f"  - significant other: {so['name']} ({so['other_type']}, {so['relation']})")

                key_prefix = f"id_{entry_idx}_{classification['id']}"
                corrected_json_text = st.text_area(
                    "Corrected claims (JSON, optional — edit to correct)",
                    value=claims_summary,
                    height=200,
                    key=f"{key_prefix}_json",
                )
                flagged = st.checkbox("Flag as mistake", key=f"{key_prefix}_flag")
                feedback = st.text_area("Feedback", key=f"{key_prefix}_feedback")

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


def main_screen():
    entries = st.session_state.entries
    entry_idx = st.session_state.entry_idx

    with get_conn() as conn:
        progress = progress_for_annotator(conn, st.session_state.annotator_name)
        st.progress(progress["fraction"], text=f"{progress['done']} / {progress['total']} rows annotated")

        if entry_idx >= len(entries):
            st.success("All entries in the pilot sample have been reviewed. Thank you!")
            return

        entry = entries[entry_idx]
        st.caption(f"Entry {entry_idx + 1} of {len(entries)} — annotator: {st.session_state.annotator_name}")

        if entry["is_self"]:
            save_payloads = render_identity(conn, entry, entry_idx)
        else:
            save_payloads = render_four_point(conn, entry, entry_idx)

        col_prev, col_save, _ = st.columns([1, 1, 3])
        with col_prev:
            if st.button("Previous", disabled=(entry_idx == 0)):
                st.session_state.entry_idx -= 1
                st.rerun()
        with col_save:
            if st.button("Save & Next", type="primary"):
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
