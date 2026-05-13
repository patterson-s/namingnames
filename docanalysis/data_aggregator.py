#!/usr/bin/env python3

import json
from typing import List, Dict, Any, Optional
from collections import defaultdict


class DataAggregator:
    @staticmethod
    def load_antagonistic_statements(file_path: str) -> List[Dict[str, Any]]:
        """Load JSONL file containing antagonistic statements"""
        statements = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # Only include antagonistic statements (classification = "1")
                    if record.get('classification') == '1':
                        statements.append(record)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping malformed JSON on line {line_num}: {e}")
                    continue
        
        return statements
    
    @staticmethod
    def aggregate_by_document(statements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate statements by doc_id"""
        documents = defaultdict(lambda: {
            'statements': [],
            'targets': set(),
            'source': None,
            'year': None,
            'doc_id': None
        })
        
        for stmt in statements:
            doc_id = stmt.get('doc_id')
            if not doc_id:
                continue
            
            doc = documents[doc_id]
            doc['statements'].append(stmt)
            doc['targets'].add(stmt.get('target'))
            doc['source'] = stmt.get('source') or stmt.get('source_country')
            doc['year'] = stmt.get('year')
            doc['doc_id'] = doc_id
        
        # Convert to list of document objects
        aggregated = []
        for doc_id, doc_data in documents.items():
            # Group statements by target
            statements_by_target = defaultdict(list)
            for stmt in doc_data['statements']:
                target = stmt.get('target')
                if target:
                    statements_by_target[target].append({
                        'text': stmt.get('text', ''),
                        'reasoning': stmt.get('reasoning', ''),
                        'chunk_id': stmt.get('chunk_id', ''),
                        'target_entities': stmt.get('target_entities', [])
                    })
            
            # Create structured document object
            document = {
                'doc_id': doc_data['doc_id'],
                'source': doc_data['source'],
                'year': doc_data['year'],
                'targets': sorted(list(doc_data['targets'])),
                'statements_by_target': dict(statements_by_target),
                'total_statements': len(doc_data['statements'])
            }
            
            # Add formatted representations
            document.update(DataAggregator._create_formatted_representations(document))
            
            aggregated.append(document)
        
        return aggregated
    
    @staticmethod
    def _create_formatted_representations(document: Dict[str, Any]) -> Dict[str, Any]:
        """Create various formatted representations of the statements"""
        formatted = {}
        
        # Create formatted text by target
        formatted_sections = []
        for target, statements in document['statements_by_target'].items():
            section = f"Target: {target}"
            for i, stmt in enumerate(statements, 1):
                section += f"\n\nStatement {i}:"
                section += f"\nText: {stmt['text']}"
                section += f"\nReasoning: {stmt['reasoning']}"
            formatted_sections.append(section)
        
        formatted['statements_by_target_formatted'] = "\n\n---\n\n".join(formatted_sections)
        
        # Create a simple formatted list of all statements
        all_statements = []
        for target, statements in document['statements_by_target'].items():
            for stmt in statements:
                all_statements.append(
                    f"Target: {target}\n"
                    f"Text: {stmt['text']}\n"
                    f"Reasoning: {stmt['reasoning']}"
                )
        
        formatted['statements_formatted'] = "\n\n---\n\n".join(all_statements)
        
        # Create JSON representations
        formatted['statements_json'] = json.dumps(document['statements_by_target'], indent=2)
        formatted['statements_by_target_json'] = json.dumps(document['statements_by_target'], indent=2)
        
        # Create a compact representation for each target
        for target in document['targets']:
            target_statements = document['statements_by_target'].get(target, [])
            formatted[f'target_{target}_statements'] = json.dumps(target_statements, indent=2)
            
            # Also create formatted version for each target
            target_formatted = []
            for stmt in target_statements:
                target_formatted.append(f"Text: {stmt['text']}\nReasoning: {stmt['reasoning']}")
            formatted[f'target_{target}_formatted'] = "\n\n".join(target_formatted)
        
        # Create targets list as string
        formatted['targets_list'] = ", ".join(document['targets'])
        
        return formatted
    
    @staticmethod
    def prepare_documents_for_execution(file_path: str) -> List[Dict[str, Any]]:
        """Main entry point: load and prepare documents for prompt execution"""
        print(f"Loading antagonistic statements from {file_path}...")
        statements = DataAggregator.load_antagonistic_statements(file_path)
        print(f"Found {len(statements)} antagonistic statements")
        
        print("Aggregating by document...")
        documents = DataAggregator.aggregate_by_document(statements)
        print(f"Aggregated into {len(documents)} documents")
        
        # Print summary
        for doc in documents:
            print(f"  - {doc['doc_id']}: {doc['total_statements']} statements targeting {doc['targets_list']}")
        
        return documents