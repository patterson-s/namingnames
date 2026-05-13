#!/usr/bin/env python3

import json
import argparse
from typing import List, Dict, Any
from collections import defaultdict, Counter
from pathlib import Path


class FullDatasetCreator:
    def __init__(self):
        self.statements = []
        self.documents = {}
    
    def load_data(self, file_path: str) -> None:
        print(f"Loading data from {file_path}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get('classification') == '1':
                        self.statements.append(record)
                except json.JSONDecodeError:
                    continue
        
        print(f"Loaded {len(self.statements)} antagonistic statements")
        self._group_by_documents()
    
    def _group_by_documents(self) -> None:
        print("Grouping by documents...")
        
        documents = defaultdict(lambda: {
            'statements': [],
            'targets': set(),
            'source': None,
            'year': None,
            'doc_id': None
        })
        
        for stmt in self.statements:
            doc_id = stmt.get('doc_id')
            if not doc_id:
                continue
            
            doc = documents[doc_id]
            doc['statements'].append({
                'text': stmt.get('text', ''),
                'target': stmt.get('target', ''),
                'chunk_id': stmt.get('chunk_id', '')
            })
            doc['targets'].add(stmt.get('target'))
            doc['source'] = stmt.get('source') or stmt.get('source_country')
            doc['year'] = stmt.get('year')
            doc['doc_id'] = doc_id
        
        # Convert to clean document format
        for doc_id, doc_data in documents.items():
            if doc_data['source'] and doc_data['year']:
                self.documents[doc_id] = {
                    'doc_id': doc_data['doc_id'],
                    'source': doc_data['source'],
                    'year': int(doc_data['year']),
                    'targets': sorted(list(doc_data['targets'])),
                    'target_count': len(doc_data['targets']),
                    'statements_by_target': self._group_statements_by_target(doc_data['statements']),
                    'total_statements': len(doc_data['statements'])
                }
        
        print(f"Prepared {len(self.documents)} documents")
    
    def _group_statements_by_target(self, statements: List[Dict]) -> Dict[str, List[Dict]]:
        grouped = defaultdict(list)
        for stmt in statements:
            target = stmt['target']
            if target:
                grouped[target].append({
                    'text': stmt['text'],
                    'chunk_id': stmt['chunk_id']
                })
        return dict(grouped)
    
    def get_all_documents(self) -> List[Dict]:
        """Return all documents without sampling"""
        print(f"Processing all {len(self.documents)} documents...")
        return list(self.documents.values())
    
    def save_full_dataset(self, documents: List[Dict], output_path: str) -> None:
        """Save all documents in the same format as training sampler"""
        print(f"Saving full dataset to {output_path}...")
        
        # Clean format consistent with training sampler
        full_dataset = []
        for doc in documents:
            dataset_doc = {
                'doc_id': doc['doc_id'],
                'source': doc['source'],
                'year': doc['year'],
                'targets': doc['targets'],
                'statements_by_target': doc['statements_by_target'],
                'total_statements': doc['total_statements'],
                'target_count': doc['target_count']
            }
            full_dataset.append(dataset_doc)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(full_dataset, f, indent=2, ensure_ascii=False)
        
        # Print comprehensive summary
        self._print_dataset_summary(documents)
    
    def _print_dataset_summary(self, documents: List[Dict]) -> None:
        """Print detailed summary of the full dataset"""
        sources = Counter(doc['source'] for doc in documents)
        years = [doc['year'] for doc in documents]
        complexity = Counter(doc['target_count'] for doc in documents)
        
        # Calculate temporal periods
        temporal_periods = {
            'early_un': (1946, 1961),
            'cold_war': (1962, 1977), 
            'transition': (1978, 1993),
            'post_cold_war': (1994, 2009),
            'contemporary': (2010, 2022)
        }
        
        period_counts = Counter()
        for doc in documents:
            year = doc['year']
            for period, (start, end) in temporal_periods.items():
                if start <= year <= end:
                    period_counts[period] += 1
                    break
            else:
                period_counts['other'] += 1
        
        # Target relationship analysis
        all_relationships = []
        target_counts = Counter()
        for doc in documents:
            source = doc['source']
            for target in doc['targets']:
                relationship = f"{source}→{target}"
                all_relationships.append(relationship)
                target_counts[target] += 1
        
        relationship_counts = Counter(all_relationships)
        
        print(f"\n" + "="*60)
        print(f"FULL DATASET SUMMARY")
        print(f"="*60)
        print(f"Total documents: {len(documents)}")
        print(f"Total statements: {sum(doc['total_statements'] for doc in documents)}")
        print(f"Year range: {min(years)} - {max(years)}")
        
        print(f"\nCOMPLEXITY DISTRIBUTION (by target count):")
        for target_count in sorted(complexity.keys()):
            count = complexity[target_count]
            percentage = (count / len(documents)) * 100
            print(f"  {target_count} target(s): {count} docs ({percentage:.1f}%)")
        
        print(f"\nTEMPORAL DISTRIBUTION:")
        for period in ['early_un', 'cold_war', 'transition', 'post_cold_war', 'contemporary', 'other']:
            count = period_counts[period]
            percentage = (count / len(documents)) * 100 if count > 0 else 0
            print(f"  {period}: {count} docs ({percentage:.1f}%)")
        
        print(f"\nTOP SOURCE COUNTRIES:")
        for source, count in sources.most_common(10):
            percentage = (count / len(documents)) * 100
            print(f"  {source}: {count} docs ({percentage:.1f}%)")
        
        print(f"\nTOP TARGET COUNTRIES:")
        for target, count in target_counts.most_common(10):
            percentage = (count / len(all_relationships)) * 100
            print(f"  {target}: {count} relationships ({percentage:.1f}%)")
        
        print(f"\nMOST FREQUENT BILATERAL RELATIONSHIPS:")
        for relationship, count in relationship_counts.most_common(10):
            percentage = (count / len(all_relationships)) * 100
            print(f"  {relationship}: {count} times ({percentage:.1f}%)")
        
        # Rare relationships (mentioned only once or twice)
        rare_relationships = [rel for rel, count in relationship_counts.items() if count <= 2]
        print(f"\nRARE RELATIONSHIPS (≤2 occurrences): {len(rare_relationships)}")
        
        print(f"\nSTATEMENT DISTRIBUTION:")
        statement_counts = [doc['total_statements'] for doc in documents]
        print(f"  Min statements per doc: {min(statement_counts)}")
        print(f"  Max statements per doc: {max(statement_counts)}")
        print(f"  Avg statements per doc: {sum(statement_counts)/len(statement_counts):.1f}")
        
        print(f"="*60)
    
    def run(self, input_path: str, output_path: str) -> None:
        """Main execution method"""
        self.load_data(input_path)
        all_documents = self.get_all_documents()
        self.save_full_dataset(all_documents, output_path)


def main():
    parser = argparse.ArgumentParser(description="Create full dataset from antagonistic statements")
    parser.add_argument("--input", required=True, help="Input JSONL file with antagonistic statements")
    parser.add_argument("--output", required=True, help="Output JSON file for full dataset")
    
    args = parser.parse_args()
    
    creator = FullDatasetCreator()
    creator.run(args.input, args.output)


if __name__ == "__main__":
    main()