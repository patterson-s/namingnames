#!/usr/bin/env python3
"""Concentric-identity annotation console (Neon-backed, multi-user).

Reads model extractions from the `concentric_results` table and autosaves
annotations to `concentric_annotations` (one blob row per annotator x speech).
Runs locally (NAMINGNAMES_NEON_DB in env / 13july2026/.env) or on Streamlit
Cloud (NAMINGNAMES_NEON_DB in st.secrets).

Run:  streamlit run eval_app.py
"""

import html as _html

import streamlit as st
import streamlit.components.v1 as components

import db
from highlight import find_quote_span
from render import assemble_spans, build_reading_html, scope_class, SCOPE_TYPES

MISSED_SLOTS = 3  # blank "false negative" rows offered per speech


# ---------------------------------------------------------------- data access
@st.cache_data(show_spinner="Loading extractions…")
def load_results():
    return db.load_results()


def render_html_iframe(doc: str, height: int) -> None:
    if hasattr(st, "iframe"):
        st.iframe(doc, height=height)
    else:
        components.html(doc, height=height, scrolling=False)


st.set_page_config(page_title="Concentric Identities — Annotation Console", layout="wide")

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
    .assess-title { font-family:'IBM Plex Mono',monospace; font-size:.72rem; letter-spacing:.16em;
                    text-transform:uppercase; color:#8a8577; margin:.1rem 0 .55rem 0; }
    div[data-testid="stExpander"] { border:1px solid #ddd8cd; border-radius:8px; background:#f6f4ef; }
    .sc-pill { display:inline-block; font-size:.68rem; font-weight:600; text-transform:uppercase;
               letter-spacing:.03em; color:#fff; padding:2px 8px; border-radius:20px; }
    .sc-regional{background:#1f8a70;} .sc-values{background:#6d4bd0;} .sc-role{background:#2f5fd0;}
    .sc-ideological{background:#c0392b;} .sc-economic{background:#b8791f;} .sc-other{background:#6b7280;}
    .reasoning { background:#f6f4ef; border:1px solid #ddd8cd; border-radius:8px; padding:10px 12px;
                 margin-bottom:12px; font-size:.82rem; line-height:1.5; color:#3a3f4a; }
    .stButton>button { border-radius:7px; font-weight:600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def scope_options(model_value):
    """Selectbox options: the fixed vocabulary, plus the model's value if novel."""
    opts = list(SCOPE_TYPES)
    if model_value and model_value not in opts:
        opts = [model_value] + opts
    return opts


def _seed(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


def seed_entry_state(annotator, record, entry_idx):
    """Populate widget session_state for this entry from prior saved work.

    Runs once per entry (guarded by a sentinel) so a refresh / return restores
    saved edits, but in-progress typing is never clobbered.
    """
    sentinel = f"e{entry_idx}_seeded"
    if st.session_state.get(sentinel):
        return

    saved = db.get_annotation(annotator, record["doc_id"])
    flags_by_idx, missed_saved, speech_fb = {}, [], ""
    if saved:
        for cf in saved.get("claim_flags") or []:
            flags_by_idx[cf.get("claim_index")] = cf
        missed_saved = saved.get("missed_identities") or []
        speech_fb = saved.get("speech_feedback") or ""

    parsed = record.get("parsed_response") or {}
    claims = parsed.get("identity_claims", []) or []
    for i, claim in enumerate(claims):
        sc = claim.get("scope_type", "other")
        assigned = claim.get("assigned_to", "self")
        key = f"e{entry_idx}_c{i}"
        cf = flags_by_idx.get(i) or {}
        corrected = cf.get("corrected") or {}
        _seed(f"{key}_fp", bool(cf.get("is_false_positive", False)))
        _seed(f"{key}_scope", corrected.get("scope_type", sc))
        _seed(f"{key}_assigned", corrected.get("assigned_to", assigned))
        _seed(f"{key}_note", cf.get("feedback") or "")

    for j in range(MISSED_SLOTS):
        key = f"e{entry_idx}_m{j}"
        m = missed_saved[j] if j < len(missed_saved) else {}
        _seed(f"{key}_label", m.get("community_label") or "")
        _seed(f"{key}_scope", m.get("scope_type") or SCOPE_TYPES[0])
        _seed(f"{key}_assigned", m.get("assigned_to") or "self")
        _seed(f"{key}_target", m.get("target_country") or "")
        _seed(f"{key}_quote", m.get("quote") or "")
        _seed(f"{key}_note", m.get("feedback") or "")

    _seed(f"e{entry_idx}_speechfb", speech_fb)
    st.session_state[sentinel] = True


def build_annotation_record(annotator, record, entry_idx):
    """Rebuild the whole per-speech annotation blob from current widget state."""
    parsed = record.get("parsed_response") or {}
    claims = parsed.get("identity_claims", []) or []
    malformed = record.get("malformed") or not parsed

    claim_flags = []
    for i, claim in enumerate(claims):
        sc = claim.get("scope_type", "other")
        assigned = claim.get("assigned_to", "self")
        key = f"e{entry_idx}_c{i}"
        fp = bool(st.session_state.get(f"{key}_fp", False))
        corr_scope = st.session_state.get(f"{key}_scope", sc)
        corr_assigned = st.session_state.get(f"{key}_assigned", assigned)
        note = (st.session_state.get(f"{key}_note") or "").strip()
        corrected = {}
        if corr_scope != sc:
            corrected["scope_type"] = corr_scope
        if corr_assigned != assigned:
            corrected["assigned_to"] = corr_assigned
        if fp or corrected or note:
            claim_flags.append(
                {
                    "claim_index": i,
                    "community_label": claim.get("community_label"),
                    "is_false_positive": fp,
                    "corrected": corrected or None,
                    "feedback": note or None,
                }
            )

    missed = []
    for j in range(MISSED_SLOTS):
        key = f"e{entry_idx}_m{j}"
        label = (st.session_state.get(f"{key}_label") or "").strip()
        if label:
            missed.append(
                {
                    "community_label": label,
                    "scope_type": st.session_state.get(f"{key}_scope", SCOPE_TYPES[0]),
                    "assigned_to": st.session_state.get(f"{key}_assigned", "self"),
                    "target_country": (st.session_state.get(f"{key}_target") or "").strip() or None,
                    "quote": (st.session_state.get(f"{key}_quote") or "").strip() or None,
                    "feedback": (st.session_state.get(f"{key}_note") or "").strip() or None,
                }
            )

    speech_feedback = (st.session_state.get(f"e{entry_idx}_speechfb") or "").strip() or None
    return {
        "annotator": annotator,
        "doc_id": record["doc_id"],
        "source": record["source"],
        "year": record["year"],
        "run_id": record.get("run_id"),
        "malformed": bool(malformed),
        "n_claims": len(claims),
        "claim_flags": claim_flags,
        "missed_identities": missed,
        "speech_feedback": speech_feedback,
    }


def _autosave(annotator, record, entry_idx):
    db.save_annotation(build_annotation_record(annotator, record, entry_idx))
    st.toast("Saved", icon="✅")


def name_entry_screen():
    st.markdown(
        '<div class="masthead"><span class="brand">Concentric Identities</span>'
        '<span class="sub">annotation console</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("Read the speech. Confirm, correct, or supplement the machine's reading of concentric identities.")

    try:
        results = load_results()
    except Exception as e:
        st.error(f"Could not load results from Neon: {e}")
        return
    if not results:
        st.warning("No extractions found in `concentric_results`. Run `python load_to_neon.py` first.")
        return

    name = st.text_input("Your name")
    st.write(f"{len(results)} speeches in this evaluation run.")

    progress = db.progress_all_annotators()
    if progress:
        with st.expander("Progress across annotators"):
            for row in progress:
                st.progress(
                    min(row["done"] / len(results), 1.0),
                    text=f'{row["name"]} — {row["done"]} / {len(results)}',
                )

    if st.button("Start / Resume session", type="primary", disabled=not name.strip()):
        st.session_state.annotator_name = name.strip()
        done = db.annotated_doc_ids(name.strip())
        idx = next((i for i, r in enumerate(results) if r["doc_id"] not in done), 0)
        st.session_state.entry_idx = idx
        st.session_state.focus_span = None
        st.rerun()


def build_groups(record):
    """One group per identity_claim, with its evidence-quote spans in the speech."""
    text = record["text"]
    parsed = record.get("parsed_response") or {}
    claims = parsed.get("identity_claims", []) or []
    groups = []
    for i, claim in enumerate(claims):
        qspans = []
        for q in claim.get("evidence_quotes", []) or []:
            sp = find_quote_span(text, q)
            if sp:
                qspans.append(sp)
        groups.append(
            {
                "card_id": f"c{i}",
                "claim_index": i,
                "scope_type": claim.get("scope_type", "other"),
                "quote_spans": qspans,
                "claim": claim,
            }
        )
    return groups, parsed


def sidebar_nav(results, done):
    with st.sidebar:
        st.markdown('<div class="assess-title">Jump to speech</div>', unsafe_allow_html=True)

        def _label(i):
            r = results[i]
            mark = "✓ " if r["doc_id"] in done else ""
            return f'{mark}{r["source_name"]} {r["year"]} · {r["doc_id"]}'

        current = st.session_state.entry_idx
        current = current if 0 <= current < len(results) else 0
        idx = st.selectbox(
            "Speech", range(len(results)), index=current,
            format_func=_label, label_visibility="collapsed",
        )
        if idx != st.session_state.entry_idx:
            st.session_state.entry_idx = idx
            st.session_state.focus_span = None
            st.rerun()


def main_screen(results):
    entry_idx = st.session_state.entry_idx
    st.markdown(
        '<div class="masthead"><span class="brand">Concentric Identities</span>'
        '<span class="sub">annotation console</span></div>',
        unsafe_allow_html=True,
    )

    annotator = st.session_state.annotator_name
    done = db.annotated_doc_ids(annotator)
    sidebar_nav(results, done)
    st.progress(
        len(done) / len(results) if results else 0.0,
        text=f"{len(done)} / {len(results)} speeches annotated · {annotator}",
    )

    if entry_idx >= len(results):
        st.success("All speeches in this run have been reviewed. Thank you!")
        return

    record = results[entry_idx]
    doc_id = record["doc_id"]
    st.markdown(
        f'<div class="entry-meta">Speech {entry_idx + 1} of {len(results)} · '
        f'{_html.escape(doc_id)} · {_html.escape(str(record["source_name"]))}</div>',
        unsafe_allow_html=True,
    )
    if doc_id in done:
        st.caption("↺ Already annotated — your saved work is loaded below and updates as you edit.")

    seed_entry_state(annotator, record, entry_idx)
    groups, parsed = build_groups(record)
    malformed = record.get("malformed") or not parsed
    assembled = assemble_spans(record["text"], groups)
    card_jump = assembled["card_jump"]
    auto_kwargs = {"annotator": annotator, "record": record, "entry_idx": entry_idx}

    st.markdown('<div class="review-title">Concentric identities in this speech</div>', unsafe_allow_html=True)
    col_read, col_assess = st.columns([1.35, 1], gap="medium")

    with col_read:
        render_html_iframe(
            build_reading_html(
                source=record["source_name"],
                year=record["year"],
                heading="Concentric identities",
                speech_html=assembled["speech_html"],
                ticks_html=assembled["ticks_html"],
                focus_span_id=st.session_state.get("focus_span"),
            ),
            800,
        )

    with col_assess:
        st.markdown('<div class="assess-title">Machine assessment</div>', unsafe_allow_html=True)
        if malformed:
            st.error("Model response was malformed — no structured claims to review.")
        if parsed.get("reasoning"):
            st.markdown(
                f'<div class="reasoning"><b>Reasoning.</b> {_html.escape(parsed["reasoning"])}</div>',
                unsafe_allow_html=True,
            )
        if not groups and not malformed:
            st.info("The model found no concentric identities in this speech. Use the section below to add any it missed.")

        for g in groups:
            i = g["claim_index"]
            claim = g["claim"]
            sc = claim.get("scope_type", "other")
            assigned = claim.get("assigned_to", "self")
            target = claim.get("target_country")
            key = f"e{entry_idx}_c{i}"
            fp_checked = st.session_state.get(f"{key}_fp", False)
            note_present = bool((st.session_state.get(f"{key}_note") or "").strip())
            header = f'{claim.get("community_label", "(unlabeled)")} — {sc}'
            if fp_checked:
                header += "  ⚑"
            if note_present:
                header += "  ✎"
            with st.expander(header, expanded=False):
                who = "self" if assigned == "self" else f"other → {target or '?'}"
                st.markdown(
                    f'<span class="sc-pill {scope_class(sc)}">{_html.escape(str(sc))}</span> '
                    f'&nbsp;<span class="entry-meta">{_html.escape(who)}</span>',
                    unsafe_allow_html=True,
                )
                for q in claim.get("evidence_quotes", []) or []:
                    st.markdown(f"> {q}")

                if card_jump.get(g["card_id"]):
                    if st.button("Jump to text →", key=f"{key}_jump"):
                        st.session_state.focus_span = card_jump[g["card_id"]]
                        st.rerun()

                st.checkbox(
                    "Flag as false positive / incorrect", key=f"{key}_fp",
                    on_change=_autosave, kwargs=auto_kwargs,
                )
                c1, c2 = st.columns(2)
                with c1:
                    st.selectbox(
                        "Correct scope_type", scope_options(sc), key=f"{key}_scope",
                        on_change=_autosave, kwargs=auto_kwargs,
                    )
                with c2:
                    st.selectbox(
                        "Correct assigned_to", ["self", "other"], key=f"{key}_assigned",
                        on_change=_autosave, kwargs=auto_kwargs,
                    )
                st.text_area(
                    "Note", key=f"{key}_note", height=70,
                    on_change=_autosave, kwargs=auto_kwargs,
                )

        # ---- false negatives: identities the model missed ----
        st.markdown('<div class="assess-title">＋ Add a missed identity</div>', unsafe_allow_html=True)
        for j in range(MISSED_SLOTS):
            key = f"e{entry_idx}_m{j}"
            with st.expander(f"Missed identity {j + 1}", expanded=(j == 0)):
                st.text_input("Community label", key=f"{key}_label", on_change=_autosave, kwargs=auto_kwargs)
                c1, c2 = st.columns(2)
                with c1:
                    st.selectbox("scope_type", SCOPE_TYPES, key=f"{key}_scope", on_change=_autosave, kwargs=auto_kwargs)
                    st.selectbox("assigned_to", ["self", "other"], key=f"{key}_assigned", on_change=_autosave, kwargs=auto_kwargs)
                with c2:
                    st.text_input("target_country (if other)", key=f"{key}_target", on_change=_autosave, kwargs=auto_kwargs)
                st.text_area("Supporting quote", key=f"{key}_quote", height=68, on_change=_autosave, kwargs=auto_kwargs)
                st.text_area("Note", key=f"{key}_note", height=68, on_change=_autosave, kwargs=auto_kwargs)

        st.text_area(
            "Overall feedback on this speech", key=f"e{entry_idx}_speechfb", height=80,
            on_change=_autosave, kwargs=auto_kwargs,
        )

    # ---- navigation / save ----
    col_prev, col_next, col_save, _ = st.columns([1, 1, 1, 2])
    with col_prev:
        if st.button("← Previous", disabled=(entry_idx == 0)):
            st.session_state.entry_idx -= 1
            st.session_state.focus_span = None
            st.rerun()
    with col_next:
        if st.button("Next →", disabled=(entry_idx >= len(results) - 1)):
            st.session_state.entry_idx += 1
            st.session_state.focus_span = None
            st.rerun()
    with col_save:
        if st.button("Save & Next →", type="primary"):
            db.save_annotation(build_annotation_record(annotator, record, entry_idx))
            st.session_state.entry_idx += 1
            st.session_state.focus_span = None
            st.rerun()


def main():
    if "annotator_name" not in st.session_state:
        name_entry_screen()
    else:
        results = load_results()
        main_screen(results)


if __name__ == "__main__":
    main()
