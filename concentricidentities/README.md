# Concentric Identities

Detects **concentric (corporate) identities** in UN General Debate speeches — the
larger communities a country assigns to **itself and to other states** (regional
blocs, communities of values, international roles, ideological camps, economic
groupings). One LLM call reads each full speech and returns a reasoning trace plus
a set of structured identity claims.

## Pipeline

Uses the `namingnames` conda env. `COHERE_API_KEY` is a machine env var; the Neon
connection string (`NAMINGNAMES_NEON_DB`) is read from `../13july2026/.env`.

```
python sample_speeches.py     # sample 10 random speeches from Neon -> data/sample_10.json
python classify.py            # Cohere command-a extraction -> output/concentric_results.jsonl
streamlit run eval_app.py     # local two-pane annotation console
```

## Coding scheme

Each claim: `community_label` (open text), `scope_type`
(`regional | values | role | ideological | economic | other`), `assigned_to`
(`self | other`), `target_country` (when `other`), and verbatim `evidence_quotes`.
See `prompts/concentric_system_prompt.md`.

## Files

| File | Purpose |
|------|---------|
| `prompts/` | System + user prompts (reasoning separated from JSON response) |
| `config.py`, `db.py` | Paths/model config; psycopg3 Neon connection |
| `sample_speeches.py` | Sample speeches, bake full text into `data/sample_10.json` |
| `classify.py` | Cohere `command-a-03-2025` extraction → `output/concentric_results.jsonl` |
| `highlight.py`, `render.py` | Evidence-quote offset finding + reading-pane HTML iframe |
| `eval_app.py` | Streamlit console: highlight quotes, flag false positives / false negatives, free-text feedback |

## Annotation output

`output/annotations.jsonl` — one line per (annotator, speech) save. Records
false-positive flags + corrections per claim, missed identities (false negatives),
and speech-level feedback. Keyed by `(annotator, doc_id)`, last write wins.
