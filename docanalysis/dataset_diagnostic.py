#!/usr/bin/env python3

import json

def analyze_extreme_documents(file_path: str):
    """Analyze documents with unusually high statement counts"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Sort by statement count
    sorted_docs = sorted(data, key=lambda x: x['total_statements'], reverse=True)
    
    print("TOP 10 DOCUMENTS BY STATEMENT COUNT:")
    print("="*80)
    
    for i, doc in enumerate(sorted_docs[:10]):
        print(f"{i+1}. {doc['doc_id']} ({doc['source']} {doc['year']})")
        print(f"   Total statements: {doc['total_statements']}")
        print(f"   Target count: {doc['target_count']}")
        print(f"   Targets: {', '.join(doc['targets'])}")
        
        # Show statement distribution by target
        for target, statements in doc['statements_by_target'].items():
            print(f"   → {target}: {len(statements)} statements")
        
        # Show first few chunk_ids to check for patterns
        all_chunks = []
        for target_statements in doc['statements_by_target'].values():
            all_chunks.extend([stmt['chunk_id'] for stmt in target_statements])
        
        unique_chunks = len(set(all_chunks))
        print(f"   Unique chunk_ids: {unique_chunks}")
        
        if unique_chunks != len(all_chunks):
            print(f"   ⚠️ DUPLICATE CHUNK_IDS DETECTED!")
        
        print()

def check_for_duplicates(file_path: str):
    """Check for potential duplicate statements"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("CHECKING FOR POTENTIAL DUPLICATES:")
    print("="*50)
    
    for doc in data:
        if doc['total_statements'] > 20:  # Focus on high-count docs
            print(f"\nDocument: {doc['doc_id']}")
            
            # Check for duplicate texts
            all_texts = []
            all_chunks = []
            
            for target, statements in doc['statements_by_target'].items():
                for stmt in statements:
                    all_texts.append(stmt['text'][:100])  # First 100 chars
                    all_chunks.append(stmt['chunk_id'])
            
            # Check duplicates
            if len(set(all_texts)) != len(all_texts):
                print(f"  ⚠️ Duplicate text content detected!")
                
            if len(set(all_chunks)) != len(all_chunks):
                print(f"  ⚠️ Duplicate chunk_ids detected!")
                duplicate_chunks = [chunk for chunk in set(all_chunks) if all_chunks.count(chunk) > 1]
                print(f"  Duplicate chunks: {duplicate_chunks[:5]}...")

if __name__ == "__main__":
    file_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_02.jsonl"
    
    analyze_extreme_documents(file_path)
    check_for_duplicates(file_path)