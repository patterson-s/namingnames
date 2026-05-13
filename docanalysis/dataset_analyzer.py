#!/usr/bin/env python3

import json
import argparse
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
from pathlib import Path


class DatasetAnalyzer:
    def __init__(self):
        self.statements = []
        self.documents = {}
        
    def load_antagonistic_statements(self, file_path: str) -> None:
        print(f"Loading antagonistic statements from {file_path}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get('classification') == '1':
                        self.statements.append(record)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping malformed JSON on line {line_num}: {e}")
                    continue
        
        print(f"Loaded {len(self.statements)} antagonistic statements")
    
    def group_by_documents(self) -> None:
        print("Grouping statements by document...")
        
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
            doc['statements'].append(stmt)
            doc['targets'].add(stmt.get('target'))
            doc['source'] = stmt.get('source') or stmt.get('source_country')
            doc['year'] = stmt.get('year')
            doc['doc_id'] = doc_id
        
        self.documents = {
            doc_id: {
                'doc_id': doc_data['doc_id'],
                'source': doc_data['source'],
                'year': doc_data['year'],
                'targets': sorted(list(doc_data['targets'])),
                'target_count': len(doc_data['targets']),
                'statement_count': len(doc_data['statements'])
            }
            for doc_id, doc_data in documents.items()
        }
        
        print(f"Grouped into {len(self.documents)} documents")
    
    def analyze_sources(self) -> Dict[str, Any]:
        source_counts = Counter(doc['source'] for doc in self.documents.values())
        
        return {
            'unique_sources': len(source_counts),
            'source_distribution': dict(source_counts.most_common()),
            'sources_list': sorted(source_counts.keys())
        }
    
    def analyze_targets(self) -> Dict[str, Any]:
        all_targets = []
        for doc in self.documents.values():
            all_targets.extend(doc['targets'])
        
        target_counts = Counter(all_targets)
        
        return {
            'unique_targets': len(target_counts),
            'target_distribution': dict(target_counts.most_common()),
            'targets_list': sorted(target_counts.keys())
        }
    
    def analyze_years(self) -> Dict[str, Any]:
        year_counts = Counter(doc['year'] for doc in self.documents.values())
        years = sorted([y for y in year_counts.keys() if y is not None])
        
        return {
            'year_range': (min(years), max(years)) if years else (None, None),
            'unique_years': len(years),
            'year_distribution': dict(sorted(year_counts.items())),
            'years_list': years
        }
    
    def analyze_document_complexity(self) -> Dict[str, Any]:
        complexity_counts = Counter(doc['target_count'] for doc in self.documents.values())
        statement_counts = Counter(doc['statement_count'] for doc in self.documents.values())
        
        complexity_examples = defaultdict(list)
        for doc in self.documents.values():
            target_count = doc['target_count']
            if len(complexity_examples[target_count]) < 3:
                complexity_examples[target_count].append(doc['doc_id'])
        
        return {
            'target_count_distribution': dict(sorted(complexity_counts.items())),
            'statement_count_distribution': dict(sorted(statement_counts.items())),
            'max_targets_per_doc': max(complexity_counts.keys()) if complexity_counts else 0,
            'max_statements_per_doc': max(statement_counts.keys()) if statement_counts else 0,
            'complexity_examples': dict(complexity_examples)
        }
    
    def analyze_bilateral_relationships(self) -> Dict[str, Any]:
        relationships = []
        relationship_counts = Counter()
        
        for doc in self.documents.values():
            source = doc['source']
            for target in doc['targets']:
                relationship = f"{source} → {target}"
                relationships.append(relationship)
                relationship_counts[relationship] += 1
        
        return {
            'unique_relationships': len(relationship_counts),
            'total_relationship_instances': len(relationships),
            'relationship_distribution': dict(relationship_counts.most_common(20)),
            'rare_relationships': [rel for rel, count in relationship_counts.items() if count == 1]
        }
    
    def print_analysis(self) -> None:
        print("\n" + "="*60)
        print("DATASET ANALYSIS REPORT")
        print("="*60)
        
        print(f"\nOVERVIEW")
        print(f"Total antagonistic statements: {len(self.statements)}")
        print(f"Total documents: {len(self.documents)}")
        
        sources = self.analyze_sources()
        print(f"\nSOURCE COUNTRIES ({sources['unique_sources']} unique)")
        for source, count in list(sources['source_distribution'].items())[:10]:
            print(f"  {source}: {count} documents")
        if sources['unique_sources'] > 10:
            print(f"  ... and {sources['unique_sources'] - 10} more")
        
        targets = self.analyze_targets()
        print(f"\nTARGET COUNTRIES ({targets['unique_targets']} unique)")
        for target, count in list(targets['target_distribution'].items())[:10]:
            print(f"  {target}: {count} mentions")
        if targets['unique_targets'] > 10:
            print(f"  ... and {targets['unique_targets'] - 10} more")
        
        years = self.analyze_years()
        print(f"\nTEMPORAL DISTRIBUTION")
        print(f"  Year range: {years['year_range'][0]} - {years['year_range'][1]}")
        print(f"  Unique years: {years['unique_years']}")
        print(f"  Documents per year (top 5):")
        for year, count in list(years['year_distribution'].items())[:5]:
            print(f"    {year}: {count} documents")
        
        complexity = self.analyze_document_complexity()
        print(f"\nDOCUMENT COMPLEXITY")
        print(f"  Max targets per document: {complexity['max_targets_per_doc']}")
        print(f"  Max statements per document: {complexity['max_statements_per_doc']}")
        print(f"  Distribution by target count:")
        for target_count, doc_count in complexity['target_count_distribution'].items():
            print(f"    {target_count} target(s): {doc_count} documents")
        print(f"  Distribution by statement count (top 10):")
        for stmt_count, doc_count in list(complexity['statement_count_distribution'].items())[:10]:
            print(f"    {stmt_count} statement(s): {doc_count} documents")
        
        relationships = self.analyze_bilateral_relationships()
        print(f"\nBILATERAL RELATIONSHIPS")
        print(f"  Unique source→target pairs: {relationships['unique_relationships']}")
        print(f"  Total relationship instances: {relationships['total_relationship_instances']}")
        print(f"  Most common relationships:")
        for relationship, count in list(relationships['relationship_distribution'].items())[:10]:
            print(f"    {relationship}: {count} instances")
        print(f"  Rare relationships (appear once): {len(relationships['rare_relationships'])}")
        
        print(f"\nSAMPLING CONSIDERATIONS")
        print(f"  • Need to balance {sources['unique_sources']} source countries")
        print(f"  • Need to represent {targets['unique_targets']} target countries") 
        print(f"  • Need to span {years['unique_years']} years")
        print(f"  • Need to handle docs with 1-{complexity['max_targets_per_doc']} targets")
        print(f"  • Need to capture {relationships['unique_relationships']} different relationships")
        print(f"  • {len(relationships['rare_relationships'])} relationships appear only once")
    
    def analyze(self, file_path: str) -> None:
        self.load_antagonistic_statements(file_path)
        self.group_by_documents()
        self.print_analysis()


def main():
    parser = argparse.ArgumentParser(description="Analyze dataset to inform sampling strategy")
    parser.add_argument("--input", required=True, help="Path to JSONL file with antagonistic statements")
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"Error: Input file {args.input} does not exist")
        return
    
    analyzer = DatasetAnalyzer()
    analyzer.analyze(args.input)


if __name__ == "__main__":
    main()