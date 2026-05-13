#!/usr/bin/env python3

import json
import argparse
import random
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict, Counter
from pathlib import Path


class TrainingSampler:
    def __init__(self, target_samples: int = 100, seed: int = 42):
        self.target_samples = target_samples
        self.seed = seed
        random.seed(seed)
        
        self.statements = []
        self.documents = {}
        
        # Temporal periods for balanced sampling
        self.temporal_periods = {
            'early_un': (1946, 1961),
            'cold_war': (1962, 1977), 
            'transition': (1978, 1993),
            'post_cold_war': (1994, 2009),
            'contemporary': (2010, 2022)
        }
        
        # Complexity strata allocation
        self.complexity_allocation = {
            1: 0.40,      # Single target
            (2, 3): 0.35, # Medium complexity  
            (4, 5): 0.20, # High complexity
            (6, 99): 0.05 # Very high complexity
        }
    
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
        print("Grouping by documents and preparing for sampling...")
        
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
        
        print(f"Prepared {len(self.documents)} documents for sampling")
    
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
    
    def _get_temporal_period(self, year: int) -> str:
        for period, (start, end) in self.temporal_periods.items():
            if start <= year <= end:
                return period
        return 'unknown'
    
    def _get_complexity_stratum(self, target_count: int) -> str:
        if target_count == 1:
            return 'single'
        elif 2 <= target_count <= 3:
            return 'medium'
        elif 4 <= target_count <= 5:
            return 'high'
        else:
            return 'very_high'
    
    def _calculate_relationship_rarity(self) -> Dict[str, int]:
        relationship_counts = Counter()
        for doc in self.documents.values():
            source = doc['source']
            for target in doc['targets']:
                relationship = f"{source}→{target}"
                relationship_counts[relationship] += 1
        return dict(relationship_counts)
    
    def _stratify_documents(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Stratify documents by complexity and temporal period"""
        strata = defaultdict(lambda: defaultdict(list))
        
        for doc in self.documents.values():
            complexity = self._get_complexity_stratum(doc['target_count'])
            period = self._get_temporal_period(doc['year'])
            strata[complexity][period].append(doc)
        
        return strata
    
    def _sample_from_stratum(self, docs: List[Dict], target_count: int, 
                           relationship_rarity: Dict[str, int]) -> List[Dict]:
        """Sample documents from a stratum with diversity considerations"""
        if len(docs) <= target_count:
            return docs
        
        # Score documents for diversity
        scored_docs = []
        for doc in docs:
            score = 0
            
            # Boost rare relationships
            for target in doc['targets']:
                relationship = f"{doc['source']}→{target}"
                rarity = relationship_rarity.get(relationship, 0)
                if rarity <= 3:  # Rare relationships
                    score += 10 / rarity
            
            # Slight boost for more recent years (but not dominant)
            score += (doc['year'] - 1946) / 1000
            
            # Boost for higher statement count (more training signal)
            score += doc['total_statements'] / 100
            
            scored_docs.append((doc, score))
        
        # Sort by score and take top candidates
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        candidates = scored_docs[:target_count * 3]  # 3x oversampling
        
        # From candidates, select with additional diversity
        selected = []
        used_sources = set()
        used_targets = set()
        
        for doc, _ in candidates:
            if len(selected) >= target_count:
                break
            
            # Diversity checks
            source_diversity = doc['source'] not in used_sources
            target_diversity = not any(t in used_targets for t in doc['targets'])
            
            if source_diversity or target_diversity or len(selected) < target_count // 2:
                selected.append(doc)
                used_sources.add(doc['source'])
                used_targets.update(doc['targets'])
        
        # Fill remaining slots randomly if needed
        remaining = [doc for doc, _ in candidates if doc not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[:target_count - len(selected)])
        
        return selected[:target_count]
    
    def sample_training_data(self) -> List[Dict]:
        """Main sampling method"""
        print(f"Sampling {self.target_samples} documents for training data...")
        
        strata = self._stratify_documents()
        relationship_rarity = self._calculate_relationship_rarity()
        
        # Calculate target counts per complexity stratum
        complexity_targets = {}
        for complexity_key, allocation in self.complexity_allocation.items():
            if isinstance(complexity_key, tuple):
                key = f"{complexity_key[0]}-{complexity_key[1]}"
            else:
                key = str(complexity_key)
            complexity_targets[key] = max(1, int(self.target_samples * allocation))
        
        print(f"Sampling allocation: {complexity_targets}")
        
        selected_docs = []
        
        # Sample from each complexity stratum
        for complexity in ['single', 'medium', 'high', 'very_high']:
            if complexity == 'single':
                target_count = complexity_targets['1']
            elif complexity == 'medium':
                target_count = complexity_targets['2-3']
            elif complexity == 'high':
                target_count = complexity_targets['4-5']
            else:
                target_count = complexity_targets['6-99']
            
            complexity_docs = []
            for period_docs in strata[complexity].values():
                complexity_docs.extend(period_docs)
            
            if not complexity_docs:
                print(f"  Warning: No documents found for {complexity} complexity")
                continue
            
            # Ensure temporal diversity within stratum
            period_targets = max(1, target_count // len(self.temporal_periods))
            stratum_selected = []
            
            for period in self.temporal_periods.keys():
                period_docs = strata[complexity][period]
                if period_docs:
                    period_sample = self._sample_from_stratum(
                        period_docs, period_targets, relationship_rarity
                    )
                    stratum_selected.extend(period_sample)
            
            # If we don't have enough from temporal sampling, fill from remaining
            if len(stratum_selected) < target_count:
                remaining_docs = [doc for doc in complexity_docs 
                                if doc not in stratum_selected]
                additional = self._sample_from_stratum(
                    remaining_docs, target_count - len(stratum_selected), 
                    relationship_rarity
                )
                stratum_selected.extend(additional)
            
            # Trim to exact target
            stratum_selected = stratum_selected[:target_count]
            selected_docs.extend(stratum_selected)
            
            print(f"  {complexity}: sampled {len(stratum_selected)} documents")
        
        print(f"Total sampled: {len(selected_docs)} documents")
        return selected_docs
    
    def save_training_data(self, selected_docs: List[Dict], output_path: str) -> None:
        """Save selected documents in training format"""
        print(f"Saving training data to {output_path}...")
        
        training_data = []
        for doc in selected_docs:
            # Clean format for training
            training_doc = {
                'doc_id': doc['doc_id'],
                'source': doc['source'],
                'year': doc['year'],
                'targets': doc['targets'],
                'statements_by_target': doc['statements_by_target'],
                'total_statements': doc['total_statements'],
                'target_count': doc['target_count']
            }
            training_data.append(training_doc)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(training_data, f, indent=2, ensure_ascii=False)
        
        # Print summary
        sources = Counter(doc['source'] for doc in selected_docs)
        periods = Counter(self._get_temporal_period(doc['year']) for doc in selected_docs)
        complexity = Counter(self._get_complexity_stratum(doc['target_count']) 
                           for doc in selected_docs)
        
        print(f"\nSAMPLING SUMMARY")
        print(f"  Total documents: {len(selected_docs)}")
        print(f"  Complexity distribution: {dict(complexity)}")
        print(f"  Temporal distribution: {dict(periods)}")
        print(f"  Top sources: {dict(sources.most_common(5))}")
        print(f"  Year range: {min(doc['year'] for doc in selected_docs)} - {max(doc['year'] for doc in selected_docs)}")
    
    def run(self, input_path: str, output_path: str) -> None:
        """Main execution method"""
        self.load_data(input_path)
        selected_docs = self.sample_training_data()
        self.save_training_data(selected_docs, output_path)


def main():
    parser = argparse.ArgumentParser(description="Sample diverse training data for finetuning")
    parser.add_argument("--input", required=True, help="Input JSONL file with antagonistic statements")
    parser.add_argument("--output", required=True, help="Output JSON file for training data")
    parser.add_argument("--samples", type=int, default=100, help="Number of documents to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    sampler = TrainingSampler(target_samples=args.samples, seed=args.seed)
    sampler.run(args.input, args.output)


if __name__ == "__main__":
    main()