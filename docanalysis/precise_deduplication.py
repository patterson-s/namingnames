#!/usr/bin/env python3

import json
from collections import defaultdict

def deduplicate_within_targets(input_path: str, output_path: str):
    """Deduplicate chunk_id + target combinations while preserving cross-target relationships"""
    
    print(f"Loading dataset from {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Original dataset: {len(data)} documents")
    
    cleaned_data = []
    total_statements_before = 0
    total_statements_after = 0
    documents_affected = 0
    duplicates_removed = 0
    
    for doc in data:
        total_statements_before += doc['total_statements']
        
        cleaned_statements_by_target = defaultdict(list)
        doc_duplicates = 0
        
        # Process each target's statements
        for target, statements in doc['statements_by_target'].items():
            seen_chunks_for_target = set()
            
            for stmt in statements:
                chunk_id = stmt['chunk_id']
                
                # Key insight: Only deduplicate within the same target
                if chunk_id not in seen_chunks_for_target:
                    seen_chunks_for_target.add(chunk_id)
                    cleaned_statements_by_target[target].append(stmt)
                else:
                    # This is a true duplicate (same chunk + same target)
                    doc_duplicates += 1
        
        # Remove targets with no statements after deduplication
        cleaned_statements_by_target = {k: v for k, v in cleaned_statements_by_target.items() if v}
        
        # Calculate new totals
        new_total_statements = sum(len(stmts) for stmts in cleaned_statements_by_target.values())
        new_target_count = len(cleaned_statements_by_target)
        new_targets = sorted(cleaned_statements_by_target.keys())
        
        # Track if document was affected
        if new_total_statements != doc['total_statements']:
            documents_affected += 1
            duplicates_removed += doc_duplicates
        
        total_statements_after += new_total_statements
        
        # Create cleaned document
        cleaned_doc = {
            'doc_id': doc['doc_id'],
            'source': doc['source'], 
            'year': doc['year'],
            'targets': new_targets,
            'statements_by_target': dict(cleaned_statements_by_target),
            'total_statements': new_total_statements,
            'target_count': new_target_count
        }
        
        # Only include documents with at least 1 statement
        if new_total_statements > 0:
            cleaned_data.append(cleaned_doc)
    
    # Save cleaned dataset
    print(f"Saving cleaned dataset to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
    
    # Print cleaning summary
    print(f"\n" + "="*60)
    print(f"PRECISE DEDUPLICATION SUMMARY")
    print(f"="*60)
    print(f"Documents before: {len(data)}")
    print(f"Documents after: {len(cleaned_data)}")
    print(f"Documents affected: {documents_affected}")
    print(f"Statements before: {total_statements_before}")
    print(f"Statements after: {total_statements_after}")
    print(f"Within-target duplicates removed: {duplicates_removed}")
    print(f"Reduction: {((total_statements_before - total_statements_after) / total_statements_before) * 100:.1f}%")
    
    # Analyze what was preserved vs removed
    print(f"\nDEDUPLICATION ANALYSIS:")
    cross_target_preserved = 0
    
    # Count how many chunks appear across multiple targets (these should be preserved)
    all_chunk_target_pairs = set()
    chunk_counts = defaultdict(int)
    
    for doc in cleaned_data:
        for target, statements in doc['statements_by_target'].items():
            for stmt in statements:
                chunk_id = stmt['chunk_id']
                all_chunk_target_pairs.add((chunk_id, target))
                chunk_counts[chunk_id] += 1
    
    cross_target_chunks = sum(1 for count in chunk_counts.values() if count > 1)
    print(f"Chunks appearing across multiple targets: {cross_target_chunks}")
    print(f"These represent legitimate multi-target statements (preserved)")
    
    # Check the previously problematic documents
    print(f"\nPREVIOUSLY PROBLEMATIC DOCUMENTS:")
    problematic_docs = ['ALB_23_1968', 'ALB_26_1971', 'ALB_34_1979', 'IRN_38_1983', 'VNM_38_1983']
    
    for doc in cleaned_data:
        if doc['doc_id'] in problematic_docs:
            original_count = next((d['total_statements'] for d in data if d['doc_id'] == doc['doc_id']), 0)
            print(f"  {doc['doc_id']}: {doc['total_statements']} statements (was {original_count})")
    
    # New statistics
    if cleaned_data:
        max_statements = max(doc['total_statements'] for doc in cleaned_data)
        max_doc = next(doc for doc in cleaned_data if doc['total_statements'] == max_statements)
        print(f"\nNew max statements per document: {max_statements}")
        print(f"Document with max statements: {max_doc['doc_id']}")
        
        # Statement distribution
        statement_counts = [doc['total_statements'] for doc in cleaned_data]
        avg_statements = sum(statement_counts) / len(statement_counts)
        print(f"Average statements per document: {avg_statements:.1f}")
    
    print(f"\n✅ Cleaned dataset saved as: {output_path}")
    print(f"This preserves cross-target relationships while removing within-target duplicates.")

def verify_deduplication(file_path: str):
    """Verify that deduplication worked correctly"""
    print(f"\nVERIFYING DEDUPLICATION...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues_found = 0
    
    for doc in data:
        for target, statements in doc['statements_by_target'].items():
            chunk_ids = [stmt['chunk_id'] for stmt in statements]
            unique_chunks = set(chunk_ids)
            
            if len(chunk_ids) != len(unique_chunks):
                print(f"❌ ISSUE: {doc['doc_id']} still has duplicate chunks for target {target}")
                issues_found += 1
    
    if issues_found == 0:
        print(f"✅ Verification passed: No within-target duplicates found")
    else:
        print(f"❌ Verification failed: {issues_found} documents still have within-target duplicates")

if __name__ == "__main__":
    input_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_02.jsonl"
    output_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_03.jsonl"
    
    deduplicate_within_targets(input_path, output_path)
    verify_deduplication(output_path)