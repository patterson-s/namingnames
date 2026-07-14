#!/usr/bin/env python3
"""One-shot loader: push concentric_results.jsonl into Neon.

Creates the tables (schema.sql) then UPSERTs each result row into
`concentric_results`, using file order as `seq` to preserve navigation order.
Idempotent — re-run whenever the sample / classification is refreshed.

Run:  python load_to_neon.py
"""

import json

import config
from db import get_conn

SCHEMA_FILE = config.BASE_DIR / "schema.sql"


def create_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()


def load_results(conn) -> int:
    if not config.RESULTS_FILE.exists():
        raise SystemExit(f"No results file at {config.RESULTS_FILE}")

    with open(config.RESULTS_FILE, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    with conn.cursor() as cur:
        for seq, r in enumerate(records):
            cur.execute(
                """
                INSERT INTO concentric_results
                    (seq, doc_id, run_id, source, source_name, year, text,
                     model_id, parsed_response, malformed, full_response,
                     processing_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, doc_id) DO UPDATE SET
                    seq                  = EXCLUDED.seq,
                    source               = EXCLUDED.source,
                    source_name          = EXCLUDED.source_name,
                    year                 = EXCLUDED.year,
                    text                 = EXCLUDED.text,
                    model_id             = EXCLUDED.model_id,
                    parsed_response      = EXCLUDED.parsed_response,
                    malformed            = EXCLUDED.malformed,
                    full_response        = EXCLUDED.full_response,
                    processing_timestamp = EXCLUDED.processing_timestamp
                """,
                (
                    seq,
                    r["doc_id"],
                    r.get("run_id"),
                    r.get("source"),
                    r.get("source_name"),
                    r.get("year"),
                    r.get("text"),
                    r.get("model_id"),
                    json.dumps(r.get("parsed_response")),
                    r.get("malformed"),
                    r.get("full_response"),
                    r.get("processing_timestamp"),
                ),
            )
    conn.commit()
    return len(records)


def main() -> None:
    with get_conn() as conn:
        create_tables(conn)
        n = load_results(conn)
    print(f"Loaded {n} results into concentric_results.")


if __name__ == "__main__":
    main()
