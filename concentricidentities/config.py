#!/usr/bin/env python3

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# The Neon connection string lives in the sibling 13july2026/.env (the corpus is
# read from there). COHERE_API_KEY is a persistent user env var on this machine.
# Load a local .env first if present, then fall back to the sibling one.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / "13july2026" / ".env")

SYSTEM_PROMPT_FILE = PROMPTS_DIR / "concentric_system_prompt.md"
USER_PROMPT_FILE = PROMPTS_DIR / "concentric_user_prompt.md"

SAMPLE_FILE = DATA_DIR / "sample_10.json"
RESULTS_FILE = OUTPUT_DIR / "concentric_results.jsonl"
ANNOTATIONS_FILE = OUTPUT_DIR / "annotations.jsonl"

MODEL_ID = "command-a-03-2025"
TEMPERATURE = 0.0
MAX_TOKENS = 8000

SAMPLE_SIZE = 10
SAMPLE_SEED = 20260714

MAX_RETRIES = 5
RETRY_DELAY = 3.0
EXPONENTIAL_BACKOFF = True

SCOPE_TYPES = ["regional", "values", "role", "ideological", "economic", "other"]


def _neon_conn_str() -> str | None:
    conn_str = os.getenv("NAMINGNAMES_NEON_DB")
    if conn_str:
        return conn_str
    try:
        import streamlit as st

        return st.secrets.get("NAMINGNAMES_NEON_DB")
    except Exception:
        return None


COHERE_API_KEY = os.getenv("COHERE_API_KEY")
NEON_CONN_STR = _neon_conn_str()
