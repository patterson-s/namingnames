#!/usr/bin/env python3

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = Path(r"C:\Users\spatt\Desktop\namingnames\namingnames\prompts")
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    scheme: str  # 'four_point' | 'identity'
    model_id: str
    system_prompt_file: Path
    user_prompt_template_file: Path
    work_items_file: Path
    max_tokens: int = 8000


RUN_CONFIGS: dict[str, RunConfig] = {
    "fourpoint_cmda_1": RunConfig(
        run_id="fourpoint_cmda_1",
        scheme="four_point",
        model_id="command-a-03-2025",
        system_prompt_file=PROMPTS_DIR / "four_point_system_prompt.md",
        user_prompt_template_file=PROMPTS_DIR / "four_point_user_prompt.md",
        work_items_file=DATA_DIR / "four_point_work_items.jsonl",
    ),
    "fourpoint_cmdaplus_1": RunConfig(
        run_id="fourpoint_cmdaplus_1",
        scheme="four_point",
        model_id="command-a-plus-05-2026",
        system_prompt_file=PROMPTS_DIR / "four_point_system_prompt.md",
        user_prompt_template_file=PROMPTS_DIR / "four_point_user_prompt.md",
        work_items_file=DATA_DIR / "four_point_work_items.jsonl",
    ),
    "identity_cmda_1": RunConfig(
        run_id="identity_cmda_1",
        scheme="identity",
        model_id="command-a-03-2025",
        system_prompt_file=PROMPTS_DIR / "identity_system_prompt.md",
        user_prompt_template_file=PROMPTS_DIR / "identity_user_prompt.md",
        work_items_file=DATA_DIR / "identity_work_items.jsonl",
    ),
    "identity_cmdaplus_1": RunConfig(
        run_id="identity_cmdaplus_1",
        scheme="identity",
        model_id="command-a-plus-05-2026",
        system_prompt_file=PROMPTS_DIR / "identity_system_prompt.md",
        user_prompt_template_file=PROMPTS_DIR / "identity_user_prompt.md",
        work_items_file=DATA_DIR / "identity_work_items.jsonl",
    ),
}


def _neon_conn_str() -> str | None:
    conn_str = os.getenv("NAMINGNAMES_NEON_DB")
    if conn_str:
        return conn_str
    try:
        import streamlit as st
        return st.secrets.get("NAMINGNAMES_NEON_DB")
    except Exception:
        return None


class Config:
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    NEON_CONN_STR = _neon_conn_str()

    MAX_WORKERS = 8
    DEFAULT_WORKERS = 5
    BATCH_SIZE = 10

    MAX_RETRIES = 5
    RETRY_DELAY = 3.0
    EXPONENTIAL_BACKOFF = True

    PROGRESS_UPDATE_INTERVAL = 60
    SHOW_WORKER_DETAILS = True

    SAMPLE_SIZE = 100
    SAMPLE_SEED = 20260713

    @classmethod
    def dirs_for_run(cls, run_id: str) -> dict[str, Path]:
        return {
            "batch_dir": OUTPUT_DIR / "batches" / run_id,
            "log_dir": OUTPUT_DIR / "logs" / run_id,
            "progress_dir": OUTPUT_DIR / "progress" / run_id,
        }

    @classmethod
    def ensure_directories(cls, run_id: str):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for path in cls.dirs_for_run(run_id).values():
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def progress_file(cls, run_id: str) -> Path:
        return cls.dirs_for_run(run_id)["progress_dir"] / "progress.json"

    @classmethod
    def failed_items_file(cls, run_id: str) -> Path:
        return cls.dirs_for_run(run_id)["log_dir"] / "failed_items.jsonl"

    @classmethod
    def validate_config(cls, run_id: str):
        if run_id not in RUN_CONFIGS:
            raise ValueError(f"Unknown run_id: {run_id}. Valid: {list(RUN_CONFIGS)}")
        run_config = RUN_CONFIGS[run_id]
        errors = []

        if not run_config.work_items_file.exists():
            errors.append(f"Work items file not found: {run_config.work_items_file} (run sampling.py first)")
        if not run_config.system_prompt_file.exists():
            errors.append(f"System prompt file not found: {run_config.system_prompt_file}")
        if not run_config.user_prompt_template_file.exists():
            errors.append(f"User prompt template not found: {run_config.user_prompt_template_file}")
        if not cls.COHERE_API_KEY:
            errors.append("COHERE_API_KEY not found in environment variables")
        if not cls.NEON_CONN_STR:
            errors.append("NAMINGNAMES_NEON_DB not found in environment variables")

        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
        return True


config = Config()
