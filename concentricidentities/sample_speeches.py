#!/usr/bin/env python3
"""Sample N random full speeches from the Neon corpus and bake their full text
into data/sample_10.json, so the classifier and eval app never need the DB again."""

import json
import random

import config
from db import get_conn


def sample_speeches(n: int = config.SAMPLE_SIZE, seed: int = config.SAMPLE_SEED):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id, iso3, year, text FROM speeches WHERE text IS NOT NULL"
            )
            rows = cur.fetchall()
        with conn.cursor() as cur:
            cur.execute("SELECT iso3, name FROM countries")
            names = {r["iso3"]: r["name"] for r in cur.fetchall()}

    rng = random.Random(seed)
    sample_size = min(n, len(rows))
    sampled = rng.sample(rows, sample_size)

    speeches = [
        {
            "doc_id": r["doc_id"],
            "source": r["iso3"],
            "source_name": names.get(r["iso3"], r["iso3"]),
            "year": r["year"],
            "text": r["text"],
        }
        for r in sampled
    ]

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.SAMPLE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"seed": seed, "n": sample_size, "speeches": speeches},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Sampled {sample_size} speeches (seed={seed}) -> {config.SAMPLE_FILE}")
    for s in speeches:
        print(f"  {s['doc_id']:<18} {s['source_name']:<28} {len(s['text']):>7} chars")


if __name__ == "__main__":
    sample_speeches()
