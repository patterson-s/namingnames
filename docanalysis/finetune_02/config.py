#!/usr/bin/env python3

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # File paths
    BASE_DIR = Path(r"C:\Users\spatt\Desktop\namingnames\docanalysis\finetune_02")
    INPUT_FILE = Path(r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_03.jsonl")
    SYSTEM_PROMPT_FILE = Path(r"C:\Users\spatt\Desktop\namingnames\docanalysis\prompts\system_prompt.txt")
    
    # Output directories
    OUTPUT_DIR = BASE_DIR / "output"
    BATCH_DIR = OUTPUT_DIR / "batches"
    LOG_DIR = OUTPUT_DIR / "logs"
    PROGRESS_DIR = OUTPUT_DIR / "progress"
    
    # Cohere API
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    COHERE_MODEL_ID = "2ce86625-b653-4715-a99b-fe73703ea9dc-ft"
    
    # Processing settings
    MAX_WORKERS = 5
    DEFAULT_WORKERS = 3
    BATCH_SIZE = 10  # Save results every N documents per worker
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    EXPONENTIAL_BACKOFF = True
    
    # Progress tracking
    PROGRESS_FILE = PROGRESS_DIR / "progress.json"
    FAILED_DOCS_FILE = LOG_DIR / "failed_documents.jsonl"
    
    # Display settings
    PROGRESS_UPDATE_INTERVAL = 60  # seconds
    SHOW_WORKER_DETAILS = True
    
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.BATCH_DIR.mkdir(exist_ok=True)
        cls.LOG_DIR.mkdir(exist_ok=True)
        cls.PROGRESS_DIR.mkdir(exist_ok=True)
    
    @classmethod
    def validate_config(cls):
        """Validate configuration and required files"""
        errors = []
        
        if not cls.INPUT_FILE.exists():
            errors.append(f"Input file not found: {cls.INPUT_FILE}")
            
        if not cls.SYSTEM_PROMPT_FILE.exists():
            errors.append(f"System prompt file not found: {cls.SYSTEM_PROMPT_FILE}")
            
        if not cls.COHERE_API_KEY:
            errors.append("COHERE_API_KEY not found in environment variables")
            
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {error}" for error in errors))
        
        return True

# Global config instance
config = Config()