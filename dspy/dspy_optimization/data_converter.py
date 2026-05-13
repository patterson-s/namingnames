import json
import dspy
from pathlib import Path
from typing import List, Dict, Any
import logging

def load_labeled_examples(file_path: str) -> List[dspy.Example]:
    """Convert labeled JSONL examples to DSPy format"""
    
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    examples = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                
                # Create DSPy example with inputs and expected outputs
                example = dspy.Example(
                    # Inputs (what goes into the program)
                    text=data.get('text', ''),
                    target=data.get('target', ''),
                    
                    # Ground truth labels (what should come out)
                    correct_classification=data.get('correct_classification', '0'),
                    correct_victims=data.get('correct_victims', ''),
                    correct_reasoning=data.get('correct_reasoning', ''),
                    
                    # Optional: keep original data for reference
                    source_country=data.get('source_country', ''),
                    year=data.get('year', 0),
                    chunk_id=data.get('chunk_id', ''),
                    
                ).with_inputs('text', 'target')  # Mark what are inputs vs labels
                
                examples.append(example)
                
            except json.JSONDecodeError as e:
                logging.warning(f"Skipping malformed line {line_num}: {e}")
            except Exception as e:
                logging.warning(f"Error processing line {line_num}: {e}")
    
    logging.info(f"Loaded {len(examples)} examples from {file_path}")
    return examples

def validate_examples(examples: List[dspy.Example]) -> Dict[str, Any]:
    """Validate and summarize the examples"""
    
    if not examples:
        return {"valid": False, "error": "No examples loaded"}
    
    # Count classifications
    positive_count = sum(1 for ex in examples if ex.correct_classification == '1')
    negative_count = len(examples) - positive_count
    
    # Check for required fields
    missing_text = sum(1 for ex in examples if not ex.text.strip())
    missing_target = sum(1 for ex in examples if not ex.target.strip())
    
    summary = {
        "valid": True,
        "total_examples": len(examples),
        "positive_classifications": positive_count,
        "negative_classifications": negative_count,
        "positive_rate": positive_count / len(examples) * 100,
        "missing_text": missing_text,
        "missing_target": missing_target,
        "years_covered": sorted(set(ex.year for ex in examples if hasattr(ex, 'year'))),
        "countries_covered": sorted(set(ex.target for ex in examples if ex.target))
    }
    
    return summary

if __name__ == "__main__":
    # Test the converter
    file_path = "../dspy_evaluation/r2/gold_standard_examples_20250714_151304.jsonl"
    
    try:
        examples = load_labeled_examples(file_path)
        summary = validate_examples(examples)
        
        print("Data Conversion Summary:")
        print("=" * 40)
        for key, value in summary.items():
            print(f"{key}: {value}")
            
        # Show a sample example
        if examples:
            print("\nSample Example:")
            print("-" * 20)
            sample = examples[0]
            print(f"Text: {sample.text[:100]}...")
            print(f"Target: {sample.target}")
            print(f"Correct Classification: {sample.correct_classification}")
            print(f"Input keys: {sample.inputs().keys()}")
            print(f"Label keys: {sample.labels().keys()}")
            
    except Exception as e:
        print(f"Error: {e}")