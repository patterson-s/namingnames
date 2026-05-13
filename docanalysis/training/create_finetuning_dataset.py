#!/usr/bin/env python3

import json
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

def load_system_prompt(system_prompt_path: str) -> str:
    """Load the system prompt from file"""
    with open(system_prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_dynamic_inputs(json_path: str) -> Dict[str, Dict[str, Any]]:
    """Load dynamic inputs from JSON array and index by doc_id"""
    inputs_by_doc_id = {}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle both array and single object formats
    if isinstance(data, list):
        items = data
    else:
        items = [data]
    
    for item in items:
        doc_id = item['doc_id']
        inputs_by_doc_id[doc_id] = item
    
    return inputs_by_doc_id

def load_training_example(training_file_path: str) -> str:
    """Load training example (expected output) from file"""
    with open(training_file_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def format_user_message(dynamic_input: Dict[str, Any]) -> str:
    """Format the dynamic input data as a user message"""
    doc_id = dynamic_input['doc_id']
    source = dynamic_input['source']
    year = dynamic_input['year']
    targets = dynamic_input['targets']
    statements = dynamic_input['statements_by_target']
    total_statements = dynamic_input['total_statements']
    target_count = dynamic_input['target_count']
    
    # Build the user message
    message_parts = []
    message_parts.append(f"Document ID: {doc_id}")
    message_parts.append(f"Source Country: {source}")
    message_parts.append(f"Year: {year}")
    message_parts.append(f"Target Countries: {', '.join(targets)}")
    message_parts.append(f"Total Antagonistic Statements: {total_statements}")
    message_parts.append("")
    
    message_parts.append("Antagonistic statements grouped by target:")
    message_parts.append("")
    
    for target, target_statements in statements.items():
        message_parts.append(f"Target: {target}")
        message_parts.append("-" * 20)
        
        for i, statement in enumerate(target_statements, 1):
            message_parts.append(f"Statement {i} (chunk_id: {statement['chunk_id']}):")
            message_parts.append(f'"{statement["text"]}"')
            message_parts.append("")
    
    message_parts.append("Please analyze these antagonistic statements following the systematic process outlined in your instructions.")
    
    return "\n".join(message_parts)

def create_training_example(system_prompt: str, user_message: str, assistant_response: str) -> Dict[str, Any]:
    """Create a single training example in Cohere format"""
    return {
        "messages": [
            {
                "role": "System",
                "content": system_prompt
            },
            {
                "role": "User", 
                "content": user_message
            },
            {
                "role": "Chatbot",
                "content": assistant_response
            }
        ]
    }

def main():
    print("🔄 Creating Fine-tuning Dataset for Diplomatic Analysis")
    print("=" * 60)
    
    # Configuration
    system_prompt_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\prompts\system_prompt.txt"
    dynamic_inputs_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_01.jsonl"
    training_dir = Path(r"C:\Users\spatt\Desktop\namingnames\docanalysis\training")
    output_path = training_dir / "diplomatic_analysis_finetune.jsonl"
    
    try:
        # Step 1: Load system prompt
        print("Step 1: Loading system prompt...")
        if not Path(system_prompt_path).exists():
            raise FileNotFoundError(f"System prompt not found: {system_prompt_path}")
        
        system_prompt = load_system_prompt(system_prompt_path)
        print(f"✅ System prompt loaded ({len(system_prompt)} characters)")
        
        # Step 2: Load dynamic inputs
        print("\nStep 2: Loading dynamic inputs...")
        if not Path(dynamic_inputs_path).exists():
            raise FileNotFoundError(f"Dynamic inputs not found: {dynamic_inputs_path}")
        
        dynamic_inputs = load_dynamic_inputs(dynamic_inputs_path)
        print(f"✅ Loaded {len(dynamic_inputs)} dynamic input examples")
        
        # Step 3: Process training examples
        print("\nStep 3: Processing training examples...")
        training_examples = []
        matched_count = 0
        missing_files = []
        
        for doc_id, dynamic_input in dynamic_inputs.items():
            # Look for corresponding training file
            training_file = training_dir / f"{doc_id}_training.txt"
            
            if training_file.exists():
                print(f"  ✅ Processing {doc_id}")
                
                # Load the training example (expected output)
                assistant_response = load_training_example(training_file)
                
                # Format the user message from dynamic input
                user_message = format_user_message(dynamic_input)
                
                # Create the training example
                training_example = create_training_example(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    assistant_response=assistant_response
                )
                
                training_examples.append(training_example)
                matched_count += 1
                
            else:
                print(f"  ❌ Missing training file for {doc_id}")
                missing_files.append(doc_id)
        
        # Step 4: Save training dataset
        print(f"\nStep 4: Saving training dataset...")
        print(f"Successfully matched: {matched_count} examples")
        print(f"Missing training files: {len(missing_files)}")
        
        if missing_files:
            print(f"Missing files for: {', '.join(missing_files)}")
        
        if matched_count == 0:
            print("❌ No training examples could be created!")
            return
        
        # Write the JSONL file
        with open(output_path, 'w', encoding='utf-8') as f:
            for example in training_examples:
                f.write(json.dumps(example) + '\n')
        
        print(f"✅ Training dataset saved to: {output_path}")
        print(f"📊 Dataset contains {len(training_examples)} training examples")
        
        # Step 5: Validate the dataset
        print(f"\nStep 5: Validating dataset format...")
        
        # Quick validation
        validation_errors = []
        for i, example in enumerate(training_examples):
            messages = example.get('messages', [])
            if len(messages) != 3:
                validation_errors.append(f"Example {i+1}: Expected 3 messages, got {len(messages)}")
            
            expected_roles = ['System', 'User', 'Chatbot']
            actual_roles = [msg.get('role') for msg in messages]
            if actual_roles != expected_roles:
                validation_errors.append(f"Example {i+1}: Invalid roles {actual_roles}")
        
        if validation_errors:
            print("❌ Validation errors found:")
            for error in validation_errors[:5]:  # Show first 5 errors
                print(f"  {error}")
            if len(validation_errors) > 5:
                print(f"  ... and {len(validation_errors) - 5} more errors")
        else:
            print("✅ Dataset format validation passed")
        
        # Summary
        print(f"\n🎉 Dataset Creation Complete!")
        print("=" * 40)
        print(f"Output file: {output_path}")
        print(f"Training examples: {len(training_examples)}")
        print(f"Success rate: {matched_count}/{len(dynamic_inputs)} ({matched_count/len(dynamic_inputs)*100:.1f}%)")
        
        if matched_count >= 2:
            print("\n✅ Ready for fine-tuning!")
            print("Next step: Use the existing cohere_finetuning.py script")
            print(f"Update training_file path to: {output_path}")
        else:
            print(f"\n⚠️ Need at least 2 examples for fine-tuning, got {matched_count}")
        
    except Exception as e:
        print(f"\n❌ Error creating dataset: {str(e)}")
        raise

if __name__ == "__main__":
    main()