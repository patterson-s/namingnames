#!/usr/bin/env python3
"""Run the concentric-identity extraction over the sampled speeches with Cohere
command-a, one LLM call per full speech. Writes output/concentric_results.jsonl.

Reuses the call/parse pattern from 13july2026/cohere_worker.py."""

import json
import re
import time
from datetime import datetime

import cohere

import config

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(response_text: str):
    """Return (parsed_dict | None, malformed_bool). json.loads first, then the
    first {...} block as a fallback."""
    try:
        return json.loads(response_text.strip()), False
    except json.JSONDecodeError:
        pass
    match = JSON_BLOCK_RE.search(response_text)
    if match:
        try:
            return json.loads(match.group(0)), False
        except json.JSONDecodeError:
            pass
    return None, True


def call_cohere(client, system_prompt: str, user_prompt: str):
    last_error = None
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            response = client.chat(
                model=config.MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=config.TEMPERATURE,
                max_tokens=config.MAX_TOKENS,
            )
            content = response.message.content
            if isinstance(content, list):
                return "".join(b.text for b in content if getattr(b, "text", None))
            return content
        except Exception as e:  # noqa: BLE001 - mirror worker's broad retry
            last_error = e
            if attempt < config.MAX_RETRIES:
                delay = config.RETRY_DELAY
                if config.EXPONENTIAL_BACKOFF:
                    delay *= 2**attempt
                print(f"  API attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                print(f"  API failed after {config.MAX_RETRIES + 1} attempts: {last_error}")
    return None


def main():
    if not config.COHERE_API_KEY:
        raise RuntimeError("COHERE_API_KEY not found in environment.")

    with open(config.SAMPLE_FILE, "r", encoding="utf-8") as f:
        speeches = json.load(f)["speeches"]

    system_prompt = config.SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    user_template = config.USER_PROMPT_FILE.read_text(encoding="utf-8").strip()

    client = cohere.ClientV2(api_key=config.COHERE_API_KEY)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n_ok = n_malformed = 0
    with open(config.RESULTS_FILE, "w", encoding="utf-8") as out:
        for i, sp in enumerate(speeches, 1):
            user_prompt = user_template.format(
                source_name=sp["source_name"],
                source_iso3=sp["source"],
                year=sp["year"],
                speech_text=sp["text"],
            )
            response_text = call_cohere(client, system_prompt, user_prompt)
            if response_text is None:
                parsed, malformed = None, True
            else:
                parsed, malformed = parse_response(response_text)

            n_claims = len(parsed.get("identity_claims", [])) if parsed else 0
            n_ok += 0 if malformed else 1
            n_malformed += 1 if malformed else 0
            print(
                f"[{i}/{len(speeches)}] {sp['doc_id']:<18} "
                f"{'MALFORMED' if malformed else f'{n_claims} claim(s)'}"
            )

            record = {
                **sp,
                "run_id": "concentric_cmda_1",
                "model_id": config.MODEL_ID,
                "parsed_response": parsed,
                "malformed": malformed,
                "full_response": response_text,
                "processing_timestamp": datetime.now().isoformat(),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nDone. {n_ok} ok, {n_malformed} malformed -> {config.RESULTS_FILE}")


if __name__ == "__main__":
    main()
