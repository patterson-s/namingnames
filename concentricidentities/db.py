#!/usr/bin/env python3
"""Neon Postgres access for the concentric-identity console.

Source results are read from `concentric_results`; human annotations are read
from / written to `concentric_annotations` (one blob row per annotator×speech).
Connection string comes from NAMINGNAMES_NEON_DB (env or st.secrets) via config.
"""

import json

import psycopg
from psycopg.rows import dict_row

import config


def get_conn() -> psycopg.Connection:
    if not config.NEON_CONN_STR:
        raise RuntimeError(
            "NAMINGNAMES_NEON_DB not found. Set it in the environment, in "
            "13july2026/.env, or in .streamlit/secrets.toml."
        )
    return psycopg.connect(config.NEON_CONN_STR, row_factory=dict_row)


# ------------------------------------------------------------------ results
def load_results() -> list[dict]:
    """All source results in navigation order, shaped like the old JSONL rows."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, run_id, source, source_name, year, text, model_id,
                   parsed_response, malformed, full_response, processing_timestamp
            FROM concentric_results
            ORDER BY seq
            """
        )
        rows = cur.fetchall()
    # psycopg returns jsonb as a dict already; datetime -> isoformat for parity.
    for r in rows:
        ts = r.get("processing_timestamp")
        if ts is not None and not isinstance(ts, str):
            r["processing_timestamp"] = ts.isoformat()
    return rows


# -------------------------------------------------------------- annotations
def annotated_doc_ids(annotator: str) -> set[str]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id FROM concentric_annotations WHERE annotator_name = %s",
            (annotator,),
        )
        return {row["doc_id"] for row in cur.fetchall()}


def get_annotation(annotator: str, doc_id: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT annotator_name, doc_id, source, year, run_id, malformed,
                   n_claims, claim_flags, missed_identities, speech_feedback,
                   annotated_at
            FROM concentric_annotations
            WHERE annotator_name = %s AND doc_id = %s
            """,
            (annotator, doc_id),
        )
        return cur.fetchone()


def save_annotation(record: dict) -> None:
    """UPSERT one per-speech annotation blob, keyed (annotator_name, doc_id)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO concentric_annotations
                    (annotator_name, doc_id, source, year, run_id, malformed,
                     n_claims, claim_flags, missed_identities, speech_feedback,
                     annotated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (annotator_name, doc_id) DO UPDATE SET
                    source            = EXCLUDED.source,
                    year              = EXCLUDED.year,
                    run_id            = EXCLUDED.run_id,
                    malformed         = EXCLUDED.malformed,
                    n_claims          = EXCLUDED.n_claims,
                    claim_flags       = EXCLUDED.claim_flags,
                    missed_identities = EXCLUDED.missed_identities,
                    speech_feedback   = EXCLUDED.speech_feedback,
                    annotated_at      = now()
                """,
                (
                    record["annotator"],
                    record["doc_id"],
                    record.get("source"),
                    record.get("year"),
                    record.get("run_id"),
                    record.get("malformed"),
                    record.get("n_claims"),
                    json.dumps(record.get("claim_flags") or []),
                    json.dumps(record.get("missed_identities") or []),
                    record.get("speech_feedback"),
                ),
            )
        conn.commit()


def progress_all_annotators() -> list[dict]:
    """[{name, done}] across all annotators, for the landing page."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT annotator_name AS name, count(*) AS done
            FROM concentric_annotations
            GROUP BY annotator_name
            ORDER BY annotator_name
            """
        )
        return cur.fetchall()
