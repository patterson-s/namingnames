#!/usr/bin/env python3

import json
from typing import List, Dict, Any, Optional, Set, Tuple

from config import DATA_DIR


def _run_label(filename: str, meta: Dict[str, Any]) -> str:
    n = meta.get("n") or len(meta.get("doc_ids", []))
    stem = filename.removeprefix("sample_").removesuffix(".json")
    return f"{stem.replace('_', ' ')} · {n} speeches"


def list_evaluation_runs() -> List[Dict[str, Any]]:
    """Every `sample_*.json` in the data dir is a selectable evaluation run.
    Drop a new sample file in and it appears in the picker — no code change."""
    runs = []
    for path in sorted(DATA_DIR.glob("sample_*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(
            {
                "file": path.name,
                "label": _run_label(path.name, meta),
                "n": meta.get("n") or len(meta.get("doc_ids", [])),
                "seed": meta.get("seed"),
                "doc_ids": meta.get("doc_ids", []),
            }
        )
    return runs


def load_sample_doc_ids(filename: str = "sample_100_speeches.json") -> List[str]:
    sample_file = DATA_DIR / filename
    with open(sample_file, "r", encoding="utf-8") as f:
        return json.load(f)["doc_ids"]


def get_speech(conn, doc_id: str) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT iso3, year, text FROM speeches WHERE doc_id = %s", (doc_id,))
        row = cur.fetchone()
    if not row:
        raise ValueError(f"Speech {doc_id} not found")
    return {"source": row["iso3"], "year": row["year"], "text": row["text"] or ""}


def get_targets_for_doc(conn, doc_id: str) -> List[Dict[str, Any]]:
    query = """
        SELECT target, MIN(c.chunk_start) AS first_offset, FALSE AS is_self
        FROM four_point_classifications fpc
        JOIN chunks c ON c.chunk_id = fpc.chunk_id
        WHERE fpc.doc_id = %s
        GROUP BY target
        UNION ALL
        SELECT target, MIN(c.chunk_start) AS first_offset, TRUE AS is_self
        FROM identity_classifications ic
        JOIN chunks c ON c.chunk_id = ic.chunk_id
        WHERE ic.doc_id = %s
        GROUP BY target
        ORDER BY first_offset
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id, doc_id))
        rows = cur.fetchall()

    if not rows:
        return []

    with conn.cursor() as cur:
        cur.execute("SELECT iso3, name FROM countries")
        names = {r["iso3"]: r["name"] for r in cur.fetchall()}

    return [
        {
            "target": r["target"],
            "target_name": names.get(r["target"], r["target"]),
            "is_self": r["is_self"],
            "first_offset": r["first_offset"],
        }
        for r in rows
    ]


def get_four_point_rows(conn, doc_id: str, target: str) -> List[Dict[str, Any]]:
    query = """
        SELECT fpc.*, c.chunk_start, c.chunk_end, c.text AS chunk_text, mr.model_name
        FROM four_point_classifications fpc
        JOIN chunks c ON c.chunk_id = fpc.chunk_id
        JOIN model_runs mr ON mr.run_id = fpc.run_id
        WHERE fpc.doc_id = %s AND fpc.target = %s
        ORDER BY c.chunk_start, fpc.run_id
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id, target))
        return cur.fetchall()


def get_identity_rows(conn, doc_id: str) -> List[Dict[str, Any]]:
    query = """
        SELECT ic.*, c.chunk_start, c.chunk_end, c.text AS chunk_text, mr.model_name
        FROM identity_classifications ic
        JOIN chunks c ON c.chunk_id = ic.chunk_id
        JOIN model_runs mr ON mr.run_id = ic.run_id
        WHERE ic.doc_id = %s
        ORDER BY c.chunk_start, ic.run_id
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id,))
        classifications = cur.fetchall()

    for classification in classifications:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM identity_claims WHERE identity_classification_id = %s ORDER BY claim_index",
                (classification["id"],),
            )
            claims = cur.fetchall()
        for claim in claims:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM identity_significant_others WHERE identity_claim_id = %s ORDER BY other_index",
                    (claim["id"],),
                )
                claim["significant_others"] = cur.fetchall()
        classification["claims"] = claims

    return classifications


def get_four_point_aggregates(conn, doc_id: str, target: str) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM four_point_aggregates
        WHERE doc_id = %s AND target = %s
        ORDER BY base_run_id, method
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id, target))
        return cur.fetchall()


def get_identity_aggregates(conn, doc_id: str) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM identity_aggregates
        WHERE doc_id = %s
        ORDER BY base_run_id, method
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_id,))
        return cur.fetchall()


def get_annotated_keys(conn, annotator_name: str) -> Set[Tuple[str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT target_table, target_id FROM annotations WHERE annotator_name = %s",
            (annotator_name,),
        )
        return {(r["target_table"], r["target_id"]) for r in cur.fetchall()}


def save_annotation(
    conn,
    *,
    annotator_name: str,
    scheme: str,
    target_table: str,
    target_id: int,
    doc_id: str,
    chunk_id: Optional[str],
    source: str,
    target: str,
    run_id: str,
    original_data: dict,
    corrected_data: Optional[dict],
    is_flagged_mistake: bool,
    feedback_text: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO annotations
                (annotator_name, scheme, target_table, target_id, doc_id, chunk_id,
                 source, target, run_id, original_data, corrected_data,
                 is_flagged_mistake, feedback_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (annotator_name, target_table, target_id)
            DO UPDATE SET
                corrected_data = EXCLUDED.corrected_data,
                is_flagged_mistake = EXCLUDED.is_flagged_mistake,
                feedback_text = EXCLUDED.feedback_text,
                annotated_at = now()
            """,
            (
                annotator_name,
                scheme,
                target_table,
                target_id,
                doc_id,
                chunk_id,
                source,
                target,
                run_id,
                json.dumps(original_data),
                json.dumps(corrected_data) if corrected_data is not None else None,
                is_flagged_mistake,
                feedback_text,
            ),
        )
    conn.commit()


def progress_for_annotator(conn, annotator_name: str) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM four_point_classifications")
        total_fp = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM identity_classifications")
        total_id = cur.fetchone()["n"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM annotations WHERE annotator_name = %s",
            (annotator_name,),
        )
        done = cur.fetchone()["n"]

    total = total_fp + total_id
    return {"done": done, "total": total, "fraction": (done / total) if total else 0.0}


def progress_all_annotators(conn) -> Dict[str, Any]:
    """DB-wide progress broken down by annotator (mirrors progress_for_annotator's
    total). Used for the per-evaluator bars on the landing page."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM four_point_classifications")
        total_fp = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM identity_classifications")
        total_id = cur.fetchone()["n"]
        cur.execute(
            "SELECT annotator_name, COUNT(*) AS done FROM annotations "
            "GROUP BY annotator_name ORDER BY done DESC"
        )
        annotators = [
            {"name": r["annotator_name"], "done": r["done"]} for r in cur.fetchall()
        ]
    return {"total": total_fp + total_id, "annotators": annotators}


def speech_progress(
    conn, annotator_name: str, doc_ids: List[str]
) -> Dict[str, Dict[str, int]]:
    """Per-speech {doc_id: {"done", "total"}} for the given annotator, scoped to
    doc_ids. A speech is complete when done >= total. Used to mark ✓ in the picker."""
    progress: Dict[str, Dict[str, int]] = {d: {"done": 0, "total": 0} for d in doc_ids}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, COUNT(*) AS n FROM four_point_classifications "
            "WHERE doc_id = ANY(%s) GROUP BY doc_id "
            "UNION ALL "
            "SELECT doc_id, COUNT(*) AS n FROM identity_classifications "
            "WHERE doc_id = ANY(%s) GROUP BY doc_id",
            (doc_ids, doc_ids),
        )
        for r in cur.fetchall():
            progress[r["doc_id"]]["total"] += r["n"]
        cur.execute(
            "SELECT doc_id, COUNT(*) AS n FROM annotations "
            "WHERE annotator_name = %s AND doc_id = ANY(%s) GROUP BY doc_id",
            (annotator_name, doc_ids),
        )
        for r in cur.fetchall():
            progress[r["doc_id"]]["done"] += r["n"]
    return progress
