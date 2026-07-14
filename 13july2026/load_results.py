#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import config, RUN_CONFIGS
from neon_db import get_conn
from batch_saver import BatchManager


def read_batch_rows(run_id: str) -> List[Dict[str, Any]]:
    rows = []
    for batch_file in BatchManager.get_all_batch_files(run_id):
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_countries(conn) -> Dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT iso3, name FROM countries")
        return {row["name"].strip().lower(): row["iso3"] for row in cur.fetchall()}


def resolve_iso3(name: str, countries_by_name: Dict[str, str]) -> Optional[str]:
    return countries_by_name.get(name.strip().lower())


def load_four_point(conn, run_id: str):
    rows = read_batch_rows(run_id)
    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            item = row["item"]
            parsed = row.get("parsed_response") or {}
            cur.execute(
                """
                INSERT INTO four_point_classifications
                    (entity_mention_id, chunk_id, doc_id, source, target, year, gpe_entity,
                     run_id, label, ambiguous, reasoning, evidence_quotes, full_response, malformed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.get("entity_mention_id"),
                    item["chunk_id"],
                    item["doc_id"],
                    item["source"],
                    item["target"],
                    item["year"],
                    item.get("gpe_entity"),
                    run_id,
                    parsed.get("label"),
                    bool(parsed.get("ambiguous", False)),
                    parsed.get("reasoning"),
                    json.dumps(parsed.get("evidence_quotes", [])) if parsed else None,
                    row.get("full_response"),
                    bool(row.get("malformed", False)),
                ),
            )
            inserted += 1
    conn.commit()
    print(f"[{run_id}] Loaded {inserted} four_point_classifications rows")


def load_identity(conn, run_id: str):
    countries_by_name = load_countries(conn)
    rows = read_batch_rows(run_id)
    n_classifications = 0
    n_claims = 0
    n_others = 0

    with conn.cursor() as cur:
        for row in rows:
            item = row["item"]
            parsed = row.get("parsed_response") or {}

            cur.execute(
                """
                INSERT INTO identity_classifications
                    (entity_mention_id, chunk_id, doc_id, source, target, year, run_id,
                     reasoning, full_response, malformed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    item.get("entity_mention_id"),
                    item["chunk_id"],
                    item["doc_id"],
                    item["source"],
                    item["source"],
                    item["year"],
                    run_id,
                    parsed.get("reasoning"),
                    row.get("full_response"),
                    bool(row.get("malformed", False)),
                ),
            )
            classification_id = cur.fetchone()["id"]
            n_classifications += 1

            for claim_index, claim in enumerate(parsed.get("identity_claims", []) or []):
                cur.execute(
                    """
                    INSERT INTO identity_claims
                        (identity_classification_id, claim_index, identity_label, valence,
                         orientation, evidence_quotes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        classification_id,
                        claim_index,
                        claim.get("identity_label", ""),
                        claim.get("valence"),
                        claim.get("orientation"),
                        json.dumps(claim.get("evidence_quotes", [])),
                    ),
                )
                claim_id = cur.fetchone()["id"]
                n_claims += 1

                for other_index, other in enumerate(claim.get("significant_others", []) or []):
                    name = other.get("name", "")
                    iso3 = resolve_iso3(name, countries_by_name) if other.get("other_type") == "state" else None
                    cur.execute(
                        """
                        INSERT INTO identity_significant_others
                            (identity_claim_id, other_index, name, iso3, other_type, relation)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            claim_id,
                            other_index,
                            name,
                            iso3,
                            other.get("other_type"),
                            other.get("relation"),
                        ),
                    )
                    n_others += 1

    conn.commit()
    print(
        f"[{run_id}] Loaded {n_classifications} identity_classifications, "
        f"{n_claims} identity_claims, {n_others} identity_significant_others"
    )


def main():
    parser = argparse.ArgumentParser(description="Load pipeline batch results into Neon")
    parser.add_argument("--run_id", action="append", choices=list(RUN_CONFIGS.keys()))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    run_ids = list(RUN_CONFIGS.keys()) if args.all else (args.run_id or [])
    if not run_ids:
        parser.error("Provide --run_id (repeatable) or --all")

    with get_conn() as conn:
        for run_id in run_ids:
            scheme = RUN_CONFIGS[run_id].scheme
            if scheme == "four_point":
                load_four_point(conn, run_id)
            else:
                load_identity(conn, run_id)


if __name__ == "__main__":
    main()
