# Dataset Report: Antagonism Classification of UN Diplomatic Speech

**Project:** Naming Names — detection of antagonistic state references in UNGDC (1946–2022)  
**Generated:** 2026-05-12  

---

## Overview

This project produced three substantive classification datasets from the UN General Debate Corpus (UNGDC). Each dataset asks the same core question — *does this speech text portray country Y antagonistically?* — but was generated with a different model, prompt design, or processing pipeline. The datasets partially overlap, contain known duplication, and differ in granularity. This report documents what each dataset contains, where it lives, what its variables mean, how overcounting occurred, and how the datasets relate to one another.

---

## The Source Data

**UNGDC corpus**  
`pydeal_type/data/raw/ungdc_1946-2022.csv`  
1,611,979 speeches from 201 countries, 1946–2022.  
Columns: `doc_id`, `iso`, `session`, `year`, `text`, `UN_REGION`.  
`doc_id` format: `{ISO3}_{SESSION}_{YEAR}` (e.g., `MEX_01_1946`).

**NER-chunked mention graph**  
`pydeal_type/data/raw/ungdc_chunk_model-v5_EntityContext_02.csv` (386 MB, 1,692,803 rows)  
Each row is one NER-detected country mention within a 200-token speech chunk.  
Key columns: `doc_id`, `chunk_id`, `source`, `year`, `chunk_start`, `chunk_end`, `original_text_length`, `text`, `gpe_entity`, `gpe_context`, `target`.  
`chunk_id` format: `{doc_id}_chunk_{N}` (e.g., `MEX_01_1946_chunk_3`).  
`gpe_entity`: the surface form detected by NER (e.g., `"United States"`, `"Americans"`).  
`target`: the resolved ISO3 country code that `gpe_entity` refers to.

This file is the backbone of datasets 1 and 2 below.

---

## Dataset 1: aggressor_05 (R7B Classifications)

| | |
|---|---|
| **Location** | `pydeal_type/runs/USA_01/prompt/aggressor_05/output/full/` |
| **Files** | `complete_v1.jsonl` (1.09 GB, 427,640 rows) · `complete_v2.jsonl` (1.30 GB, 520,269 rows) |
| **Model** | `command-r7b-12-2024` (Cohere) |
| **Coverage** | 1946–2022 · 201 source countries · 202 target countries |
| **Granularity** | One row per **(chunk_id × gpe_entity × target)** |

### Variables

| Column | Type | Notes |
|--------|------|-------|
| `doc_id` | string | Speech identifier |
| `chunk_id` | string | Chunk within speech |
| `source` | ISO3 | Country delivering the speech |
| `year` | int | Session year |
| `chunk_start` / `chunk_end` | int | Character offsets into original speech |
| `original_text_length` | int | Full speech length in characters |
| `text` | string | The chunk text that was classified |
| `gpe_entity` | string | Surface form of entity mention (e.g., `"Soviet Union"`) |
| `gpe_context` | string | NER context window around the entity |
| `target` | ISO3 | Country being discussed |
| `full_response` | string | Raw LLM output (structured markdown) |
| `classification` | int (0/1) | 0 = not antagonistic · 1 = antagonistic |
| `victims` | string | Countries portrayed as victims in the text |
| `reasoning` | string | LLM's stated rationale for the classification |

### What v1 and v2 Are

Both files are outputs of the same prompt variant (`aggressor_05`) run against the same underlying chunk data. v2 was a subsequent run — likely produced after revising the parsing or batch management logic. They cover the same year range and use the same model.

**v1/v2 overlap:** 367,228 of 398,685 unique (chunk, target, gpe_entity) triples in v1 also appear in v2. The two files are not independent; v2 is largely a re-run of v1's data with some additions.

**Where they differ:**  
- 31,457 (chunk, target, entity) triples appear only in v1  
- 10,979 appear only in v2  
- ~10.4% of shared records have a different classification between v1 and v2 (model non-determinism / prompt sensitivity)

---

## Dataset 2: Multi-Model Evaluation (final_df)

| | |
|---|---|
| **Location** | `pydeal_type/evaluation/final_df.jsonl` |
| **Size** | 3.51 GB · 976,056 rows |
| **Models** | `r7b_1` (partial) · `r7b_2` (complete) · `rplus_1` (complete) |
| **Granularity** | One row per **(chunk_id × gpe_entity × target)** |

This file consolidates three model runs into a single wide-format table for cross-model comparison. It uses the same chunk-level granularity as Dataset 1.

### Variables

Core identifiers (same as Dataset 1):  
`doc_id`, `chunk_id`, `source`, `year`, `chunk_start`, `chunk_end`, `text`, `gpe_entity`, `target`

Then three sets of model output columns, one per model run:

| Suffix | Model | Coverage |
|--------|-------|----------|
| `_r7b_1` | `command-r7b-12-2024` (earlier run) | Partial — many null rows |
| `_r7b_2` | `command-r7b-12-2024` (later run) | Complete |
| `_rplus_1` | `command-r-plus-08-2024` | Complete |

Per-model columns (e.g., for `_r7b_2`):  
`full_response_r7b_2`, `classification_r7b_2`, `victims_r7b_2`, `reasoning_r7b_2`, `malformed_r7b_2`, `classification_clean_r7b_2`

`classification_clean_*` is the post-processed version of `classification_*` (normalised to int 0/1, nulls resolved).  
`malformed_*` flags records where the LLM output could not be parsed.  
The `r7b_1` columns are null for most rows — that run was applied to a subset only.

### Relationship to Dataset 1

Dataset 2's `r7b_2` column is the same model and prompt family as Dataset 1 (`aggressor_05`). `final_df` is best understood as the evaluation layer built on top of the raw run outputs.

---

## Dataset 3: Namingnames Ensemble (Fine-Tuned Model)

| | |
|---|---|
| **Location** | `namingnames/finetune/ensemble/ensemble_6aug2025.jsonl` |
| **Size** | 832 MB · 199,040 rows |
| **Model** | Cohere fine-tuned Command A (`2ce86625-b653-4715-a99b-fe73703ea9dc-ft`) |
| **Coverage** | 1946–2022 · 201 source countries · 202 target countries |
| **Granularity** | One row per **(doc_id × target)** — document level, not chunk level |

### Variables

| Column | Type | Notes |
|--------|------|-------|
| `doc_id` | string | Matches pydeal_type `doc_id` format |
| `chunk_id` | string | Non-standard format: `{ISO3}_{SESSION}_{YEAR}` without zero-padding or `_chunk_N` suffix (e.g., `BEL_2_1946`) — effectively a doc-level identifier |
| `source` / `source_country` | ISO3 | Country delivering the speech (duplicated columns) |
| `target` | ISO3 | Country being discussed |
| `target_entities` | list (as string) | Surface forms of the target found in text |
| `year` | int | Session year |
| `text` | string | The text segment that was classified |
| `reasoning` | string | Model's analytical reasoning |
| `classification` | int (0/1) | 0 = not antagonistic · 1 = antagonistic |
| `raw_classification_response` | string | Raw model output before parsing |
| `processed_at` | timestamp | When the record was generated |
| `has_error` | bool | Whether the API call encountered an error |

### Key Difference from Datasets 1 and 2

Datasets 1 and 2 operate at the **chunk level** — a single speech is broken into ~200-token windows, and each window is classified independently. Dataset 3 operates at the **document level** — the full speech (or a larger segment) is the unit of analysis. This means:

- A doc_id in Dataset 3 maps to multiple chunk_ids in Datasets 1 and 2
- `chunk_id` in Dataset 3 cannot be used to join to the NER chunk table — use `doc_id` instead
- Positive classifications in Dataset 3 may reflect antagonism anywhere in the full speech, whereas Datasets 1 and 2 localise it to a specific passage

---

## Overcounting: What Happened and Why

Naive row counts substantially overstate the number of distinct classified relationships. The overcounting factor on antagonistic (class=1) records is approximately **2.1× in both datasets**.

### Source 1: Multiple gpe_entity surface forms per (chunk, target)

The NER pipeline tags every distinct surface form of a country mention within a chunk. A single chunk that contains "United States", "Americans", and "Washington" — all referring to `USA` — generates **three separate rows**, each independently classified. These all represent a single analytical unit: *does this chunk portray USA antagonistically?* The per-entity row structure was useful for provenance but became overcounting when rows were summed without deduplication.

### Source 2: v1 / v2 overlap in Dataset 1

367,228 of the unique (chunk, target, gpe_entity) triples in `complete_v1.jsonl` also appear in `complete_v2.jsonl`. Any analysis that read both files and summed classifications double-counted those records.

### Source 3: Batch re-run concatenation

Some year-batches were processed multiple times (e.g., due to pipeline restarts) and the outputs were concatenated without deduplication before the final files were written. This creates exact-duplicate rows within a single file.

### True unique units

| Dataset | Raw rows | Unique analytical units | True class=1 | Naive class=1 | Factor |
|---------|----------|------------------------|--------------|---------------|--------|
| aggressor_05 (v1 + v2 combined) | 947,909 | 374,810 `(chunk_id, target)` | ~47,105 | 100,285 | **2.13×** |
| namingnames ensemble | 199,040 | 114,323 `(doc_id, target)` | ~12,941 | 27,776 | **2.15×** |

### Classification inconsistency across duplicates

Not all duplicates agree. Across the repeated appearances of the same analytical unit:

| Dataset | Consistently 0 | Consistently 1 | Mixed 0/1 |
|---------|---------------|----------------|-----------|
| aggressor_05 v1+v2 | 87.4% | 5.5% | 7.1% |
| namingnames ensemble | 88.7% | 6.6% | 4.7% |

The 7% / 5% of units with mixed classifications are not errors to be discarded — they are **natural prompt stability / model reliability data**. The same passage, classified twice under the same prompt, produced different results. This variance is informative about where the model is uncertain and can be used to characterise classification confidence without a separate held-out set.

---

## How the Datasets Fit Together

```
UNGDC speeches (1.6M)
        │
        ▼
NER chunking → chunk-level mention graph (1.7M rows)
        │                    │
        │                    │
        ▼                    ▼
Dataset 1                Dataset 2
aggressor_05             final_df.jsonl
(R7B, raw run)           (R7B × 2 + R+, wide comparison)
374,810 unique           976,056 rows
(chunk, target)          chunk × target
        │
        │  same underlying data, different model
        │
        ▼
Dataset 3
namingnames ensemble
(fine-tuned Command A)
114,323 unique
(doc, target)
```

**Join keys:**
- Datasets 1 ↔ 2: join on `chunk_id` + `target`  
- Datasets 1/2 ↔ 3: join on `doc_id` + `target` (chunk-level data fans out to doc-level)  
- All datasets ↔ raw speeches: join on `doc_id`  
- All datasets ↔ chunk table: join on `chunk_id` (Datasets 1/2 only)

**Analytical recommendations:**
- For the primary antagonism measure, deduplicate Dataset 1 or Dataset 2 at `(chunk_id, target)` before counting
- Use mixed-classification units (7% of Dataset 1) as a built-in reliability benchmark — their classification spread measures prompt sensitivity
- Dataset 3 (fine-tuned model) provides an independent classification signal; compare its `(doc_id, target)` positives against the aggregated chunk-level positives from Datasets 1/2 to assess model-to-model agreement
- The `classification_clean_*` columns in Dataset 2 are already normalised — prefer those over raw `classification_*` for any quantitative analysis

---

## File Inventory

| File | Repo | Size | Rows |
|------|------|------|------|
| `data/raw/ungdc_1946-2022.csv` | pydeal_type | 186 MB | 1,611,979 |
| `data/raw/ungdc_chunk_model-v5_EntityContext_02.csv` | pydeal_type | 386 MB | 1,692,803 |
| `runs/USA_01/prompt/aggressor_05/output/full/complete_v1.jsonl` | pydeal_type | 1.09 GB | 427,640 |
| `runs/USA_01/prompt/aggressor_05/output/full/complete_v2.jsonl` | pydeal_type | 1.30 GB | 520,269 |
| `evaluation/final_df.jsonl` | pydeal_type | 3.51 GB | 976,056 |
| `finetune/ensemble/ensemble_6aug2025.jsonl` | namingnames | 832 MB | 199,040 |
