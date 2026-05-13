#!/usr/bin/env python3

import json
import argparse
import time
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from data_aggregator import DataAggregator
from template_processor import TemplateProcessor
from cohere_client import CohereClient


class DiplomaticAnalysisExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = CohereClient()
        self.results = []
    
    def load_prompts(self) -> tuple[Optional[str], str]:
        """Load system and user prompts from files"""
        system_prompt = None
        
        system_prompt_path = Path("prompts/system_prompt.txt")
        if system_prompt_path.exists():
            with open(system_prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read().strip()
            print("Loaded system prompt")
        else:
            print("No system prompt found (optional)")
        
        user_prompt_path = Path("prompts/user_prompt.txt")
        if not user_prompt_path.exists():
            raise FileNotFoundError("User prompt not found at prompts/user_prompt.txt")
        
        with open(user_prompt_path, 'r', encoding='utf-8') as f:
            user_prompt = f.read().strip()
        
        print("Loaded user prompt")
        return system_prompt, user_prompt
    
    def extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract full JSON from response including code fences and analysis tags"""
        print("\n[DEBUG] full raw response start\n" + response + "\n[DEBUG] raw response end\n")

        # 1) Extract between <analysis> tags
        analysis_match = re.search(r'<analysis>(.*?)</analysis>', response, re.DOTALL)
        if analysis_match:
            block = analysis_match.group(1)
            # Extract between ``` or triple backticks
            code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', block, re.DOTALL)
            if code_match:
                json_text = code_match.group(1)
                print(f"[DEBUG] Extracted JSON code-fence block:\n{json_text}")
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] JSON decode error in code-fence block: {e}")
            else:
                # No fenced block, try raw block
                raw = block.strip()
                # Check if it starts with { and ends with }
                if raw.startswith('{') and raw.endswith('}'):
                    print(f"[DEBUG] Extracted raw JSON from analysis block:\n{raw}")
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError as e:
                        print(f"[DEBUG] JSON decode error in raw analysis block: {e}")

        # 2) Fallback: entire JSON object including top-level fields
        # Regex to capture object with bilateral_relationships key
        full_json_pattern = r'\{[^{}]*"bilateral_relationships".*?\}\s*\}'
        full_match = re.search(full_json_pattern, response, re.DOTALL)
        if full_match:
            candidate = full_match.group(0)
            print(f"[DEBUG] Found full JSON candidate:\n{candidate}")
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                print(f"[DEBUG] JSON decode error in full candidate: {e}")

        print("[DEBUG] No valid JSON extracted")
        return None
    
    def process_document(self, document: Dict[str, Any], user_prompt: str,
                         system_prompt: Optional[str], attempt: int = 1) -> Dict[str, Any]:
        """Process a single document"""
        doc_id = document['doc_id']
        print(f"  Processing {doc_id} (attempt {attempt})")

        variables = TemplateProcessor.prepare_document_variables(document)
        filled_user = TemplateProcessor.substitute_variables(user_prompt, variables)
        filled_system = TemplateProcessor.substitute_variables(system_prompt, variables) if system_prompt else None

        response = self.client.generate(
            user_prompt=filled_user,
            system_prompt=filled_system,
            model=self.config.get('model'),
            temperature=self.config.get('temperature'),
            max_tokens=self.config.get('max_tokens'),
            p=self.config.get('p'),
            k=self.config.get('k'),
            frequency_penalty=self.config.get('frequency_penalty'),
            presence_penalty=self.config.get('presence_penalty'),
            seed=self.config.get('seed')
        )

        print(f"[DEBUG] raw_response for {doc_id}:\n{response}\n")

        analysis_json = self.extract_json_from_response(response)
        status = 'success' if analysis_json else 'json_extraction_failed'

        return {
            'doc_id': doc_id,
            'source': document['source'],
            'year': document['year'],
            'targets': document['targets'],
            'total_statements': document['total_statements'],
            'raw_response': response,
            'analysis': analysis_json,
            'status': status,
            'attempt': attempt
        }
    
    def execute(self, input_file: str, output_file: str):
        system_prompt, user_prompt = self.load_prompts()
        documents = DataAggregator.prepare_documents_for_execution(input_file)
        if not documents:
            print("No documents to process")
            return

        cfg = self.config.get('batch_processing', {})
        batch_size = cfg.get('batch_size', 10)
        retries = cfg.get('max_retries', 2)
        total = len(documents)
        batches = (total + batch_size - 1) // batch_size

        print(f"Batch processing configuration:\n  Total documents: {total}\n  Batch size: {batch_size}\n  Total batches: {batches}\n  Max retries: {retries}")

        all_results: List[Dict[str, Any]] = []
        idx = 0
        for batch_num in range(1, batches + 1):
            start = idx
            end = min(idx + batch_size, total)
            batch_docs = documents[start:end]
            print(f"\nProcessing batch {batch_num}/{batches} ({len(batch_docs)} documents)")
            for doc in batch_docs:
                for attempt in range(1, retries + 2):
                    result = self.process_document(doc, user_prompt, system_prompt, attempt)
                    if result['status'] == 'success':
                        print(f"  Document {result['doc_id']} ✓")
                        break
                    else:
                        print(f"  Document {result['doc_id']} ✗ (attempt {attempt})")
                        time.sleep(2 ** attempt)
                all_results.append(result)

            idx = end
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            print(f"Progress: {idx}/{total} documents processed")

        succ = sum(1 for r in all_results if r['status'] == 'success')
        fail = sum(1 for r in all_results if r['status'] != 'success')
        print(f"\nProcessed {total}: {succ} succeeded, {fail} failed. Results in {output_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    if Path(args.config).exists():
        config = json.load(open(args.config))
        print(f"Loaded configuration from {args.config}")
    else:
        config = {
            'model': 'command-a-03-2025',
            'temperature': 0.3,
            'max_tokens': 8000,
            'p': 0.75,
            'k': 0,
            'frequency_penalty': 0.0,
            'presence_penalty': 0.0,
            'batch_processing': {'batch_size': 10, 'max_retries': 2}
        }
        print("Using default configuration")

    executor = DiplomaticAnalysisExecutor(config)
    executor.execute(args.input, args.output)

if __name__ == "__main__":
    main()
