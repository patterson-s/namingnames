-- Concentric Identities — Neon Postgres schema.
-- Idempotent: safe to run repeatedly.

-- Source classification results (one row per speech in a run).
-- Loaded by load_to_neon.py from output/concentric_results.jsonl.
CREATE TABLE IF NOT EXISTS concentric_results (
    seq                  int,                 -- preserves sample / navigation order
    doc_id               text,
    run_id               text,
    source               text,
    source_name          text,
    year                 int,
    text                 text,
    model_id             text,
    parsed_response      jsonb,               -- {reasoning, identity_claims:[...]} | null
    malformed            boolean,
    full_response        text,
    processing_timestamp timestamptz,
    PRIMARY KEY (run_id, doc_id)
);

-- Human annotations (one blob row per annotator per speech).
-- Written by the Streamlit app via db.save_annotation (autosave UPSERT).
CREATE TABLE IF NOT EXISTS concentric_annotations (
    annotator_name    text NOT NULL,
    doc_id            text NOT NULL,
    source            text,
    year              int,
    run_id            text,
    malformed         boolean,
    n_claims          int,
    claim_flags       jsonb,   -- [{claim_index, community_label, is_false_positive, corrected, feedback}]
    missed_identities jsonb,   -- [{community_label, scope_type, assigned_to, target_country, quote, feedback}]
    speech_feedback   text,
    annotated_at      timestamptz DEFAULT now(),
    PRIMARY KEY (annotator_name, doc_id)
);
