#!/usr/bin/env python3

import os
from pathlib import Path

# Create necessary directories
dirs = ["prompts", "data", "output"]
for d in dirs:
    Path(d).mkdir(exist_ok=True)
    print(f"✓ Directory '{d}' ready")

# Check for prompts
if not Path("prompts/system_prompt.txt").exists():
    print("⚠ Missing prompts/system_prompt.txt - please add your system prompt")
else:
    print("✓ System prompt found")

if not Path("prompts/user_prompt.txt").exists():
    print("⚠ Missing prompts/user_prompt.txt - please add your user prompt")
else:
    print("✓ User prompt found")

print("\nSetup complete! Next steps:")
print("1. Set your API key: set COHERE_API_KEY=your-key-here")
print("2. Run: python execute_analysis.py --input data/your_file.jsonl --output output/results.json")