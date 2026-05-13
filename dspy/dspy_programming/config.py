import dspy
import os
from dotenv import load_dotenv

def setup_dspy_cohere():
    """Configure DSPy with Cohere model matching original parameters"""
    load_dotenv()
    
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise ValueError("COHERE_API_KEY not found in environment")
    
    # Configure with Command-A (newer model)
    lm = dspy.LM(
        'cohere/command-a-03-2025',  # Changed from command-r7b-12-2024
        api_key=api_key,
        temperature=0.7,
        max_tokens=4096
    )
    
    dspy.configure(lm=lm)
    return lm