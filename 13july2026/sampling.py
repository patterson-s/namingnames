#!/usr/bin/env python3

import json
import random
from typing import List, Dict, Any, Tuple

from config import config, DATA_DIR
from neon_db import get_conn


def sample_speech_doc_ids(conn, n: int = config.SAMPLE_SIZE, seed: int = config.SAMPLE_SEED) -> List[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT doc_id FROM speeches WHERE text IS NOT NULL")
        all_doc_ids = [row["doc_id"] for row in cur.fetchall()]

    rng = random.Random(seed)
    sample_size = min(n, len(all_doc_ids))
    sampled = rng.sample(all_doc_ids, sample_size)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sample_file = DATA_DIR / "sample_100_speeches.json"
    with open(sample_file, "w", encoding="utf-8") as f:
        json.dump({"seed": seed, "n": sample_size, "doc_ids": sampled}, f, indent=2)

    print(f"Sampled {sample_size} speeches (seed={seed}) -> {sample_file}")
    return sampled


def build_work_items(conn, doc_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    query = """
        SELECT
            em.chunk_id,
            em.doc_id,
            em.source,
            em.target,
            em.year,
            MIN(em.id) AS entity_mention_id,
            string_agg(DISTINCT em.gpe_entity, ', ') AS gpe_entity,
            c.text AS chunk_text
        FROM entity_mentions em
        JOIN chunks c ON c.chunk_id = em.chunk_id
        WHERE em.doc_id = ANY(%s)
        GROUP BY em.chunk_id, em.doc_id, em.source, em.target, em.year, c.text
        ORDER BY em.doc_id, em.chunk_id, em.target
    """
    with conn.cursor() as cur:
        cur.execute(query, (doc_ids,))
        rows = cur.fetchall()

    four_point_items = []
    identity_items = []

    for row in rows:
        if row["source"] != row["target"]:
            four_point_items.append(
                {
                    "work_id": f"{row['chunk_id']}::{row['target']}",
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "source": row["source"],
                    "target": row["target"],
                    "year": row["year"],
                    "gpe_entity": row["gpe_entity"],
                    "chunk_text": row["chunk_text"],
                    "entity_mention_id": row["entity_mention_id"],
                }
            )
        else:
            identity_items.append(
                {
                    "work_id": f"{row['chunk_id']}::self",
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "source": row["source"],
                    "year": row["year"],
                    "chunk_text": row["chunk_text"],
                    "entity_mention_id": row["entity_mention_id"],
                }
            )

    return four_point_items, identity_items


def write_jsonl(items: List[Dict[str, Any]], path):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Wrote {len(items)} items -> {path}")


def main():
    with get_conn() as conn:
        doc_ids = sample_speech_doc_ids(conn)
        four_point_items, identity_items = build_work_items(conn, doc_ids)

    write_jsonl(four_point_items, DATA_DIR / "four_point_work_items.jsonl")
    write_jsonl(identity_items, DATA_DIR / "identity_work_items.jsonl")

    print(
        f"\nDone. {len(doc_ids)} speeches -> "
        f"{len(four_point_items)} four-point items, {len(identity_items)} identity items."
    )


if __name__ == "__main__":
    main()
