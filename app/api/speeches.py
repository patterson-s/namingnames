from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db import get_conn

router = APIRouter(prefix="/api")


# ── Response models ──────────────────────────────────────────────────────────

class Country(BaseModel):
    iso3: str
    name: str
    un_region: Optional[str]
    n_speeches: int


class YearEntry(BaseModel):
    year: int
    doc_id: str


class EntitySpan(BaseModel):
    mention_id: int
    start: int
    end: int
    target: str
    target_name: str
    gpe_entity: str
    chunk_start: Optional[int]
    chunk_end: Optional[int]
    classification_clean: Optional[int]
    reasoning: Optional[str]
    prop_antagonistic: Optional[float]
    n_chunks_mentioning: Optional[int]
    n_antagonistic: Optional[int]


class SpeechResponse(BaseModel):
    doc_id: str
    source: str
    year: int
    text: str
    spans: list[EntitySpan]


# ── Endpoints (sync — FastAPI runs these in a thread pool) ───────────────────

@router.get("/countries", response_model=list[Country])
def list_countries():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.iso3, c.name, c.un_region, COUNT(s.doc_id)::int AS n_speeches
            FROM countries c
            LEFT JOIN speeches s ON s.iso3 = c.iso3
            GROUP BY c.iso3, c.name, c.un_region
            ORDER BY c.name
            """
        ).fetchall()
    return [Country(**r) for r in rows]


@router.get("/countries/{iso3}/years", response_model=list[YearEntry])
def list_years(iso3: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT year, doc_id FROM speeches WHERE iso3 = %s ORDER BY year",
            (iso3.upper(),),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No speeches found for {iso3}")
    return [YearEntry(**r) for r in rows]


@router.get("/speech/{doc_id}", response_model=SpeechResponse)
def get_speech(doc_id: str):
    with get_conn() as conn:
        speech = conn.execute(
            "SELECT iso3, year, text FROM speeches WHERE doc_id = %s",
            (doc_id,),
        ).fetchone()
        if not speech:
            raise HTTPException(status_code=404, detail=f"Speech {doc_id} not found")

        rows = conn.execute(
            """
            SELECT
                em.id                        AS mention_id,
                em.target,
                co.name                      AS target_name,
                em.gpe_entity,
                c.chunk_start,
                c.chunk_end,
                c.text                       AS chunk_text,
                cc.classification_clean,
                cc.reasoning,
                dyo.prop_chunks_antagonistic  AS prop_antagonistic,
                dyo.n_chunks_mentioning,
                dyo.n_chunks_antagonistic     AS n_antagonistic
            FROM entity_mentions em
            JOIN chunks c     ON c.chunk_id  = em.chunk_id
            JOIN countries co ON co.iso3     = em.target
            LEFT JOIN chunk_classifications cc
                ON cc.entity_mention_id = em.id AND cc.run_id = 'r7b_2'
            LEFT JOIN dyadic_observations dyo
                ON dyo.source = em.source AND dyo.target = em.target AND dyo.year = em.year
            WHERE em.doc_id = %s
            ORDER BY c.chunk_start, em.gpe_entity
            """,
            (doc_id,),
        ).fetchall()

    source = speech["iso3"]
    year   = speech["year"]
    text   = speech["text"] or ""

    spans: list[EntitySpan] = []
    seen: list[tuple[int, int]] = []

    for r in rows:
        entity     = r["gpe_entity"] or ""
        chunk_text = r["chunk_text"] or ""
        chunk_start = r["chunk_start"] or 0

        if not entity or not chunk_text or not text:
            continue

        # Find all occurrences of entity within chunk_text
        offset = 0
        while True:
            idx = chunk_text.find(entity, offset)
            if idx == -1:
                idx = chunk_text.lower().find(entity.lower(), offset)
                if idx == -1:
                    break

            abs_start = chunk_start + idx
            abs_end   = chunk_start + idx + len(entity)

            if abs_end > len(text):
                break

            overlap = any(not (abs_end <= s or abs_start >= e) for s, e in seen)
            if not overlap:
                seen.append((abs_start, abs_end))
                spans.append(EntitySpan(
                    mention_id=r["mention_id"],
                    start=abs_start,
                    end=abs_end,
                    target=r["target"],
                    target_name=r["target_name"] or r["target"],
                    gpe_entity=entity,
                    chunk_start=r["chunk_start"],
                    chunk_end=r["chunk_end"],
                    classification_clean=r["classification_clean"],
                    reasoning=r["reasoning"],
                    prop_antagonistic=r["prop_antagonistic"],
                    n_chunks_mentioning=r["n_chunks_mentioning"],
                    n_antagonistic=r["n_antagonistic"],
                ))

            offset = idx + len(entity)

    spans.sort(key=lambda s: s.start)
    return SpeechResponse(doc_id=doc_id, source=source, year=year, text=text, spans=spans)
