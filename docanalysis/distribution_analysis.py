#!/usr/bin/env python3

import json
import statistics
from collections import Counter

def analyze_statement_distribution(file_path: str):
    """Analyze the distribution of statements per document"""
    
    print(f"Loading cleaned dataset from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract statement counts
    statement_counts = [doc['total_statements'] for doc in data]
    
    # Basic statistics
    total_docs = len(statement_counts)
    total_statements = sum(statement_counts)
    mean = statistics.mean(statement_counts)
    median = statistics.median(statement_counts)
    
    # Mode (most common count)
    count_frequency = Counter(statement_counts)
    mode_count, mode_frequency = count_frequency.most_common(1)[0]
    
    # Quartiles and other percentiles
    statement_counts_sorted = sorted(statement_counts)
    q1 = statistics.quantiles(statement_counts_sorted, n=4)[0]
    q3 = statistics.quantiles(statement_counts_sorted, n=4)[2]
    p90 = statistics.quantiles(statement_counts_sorted, n=10)[8]  # 90th percentile
    p95 = statistics.quantiles(statement_counts_sorted, n=20)[18]  # 95th percentile
    p99 = statistics.quantiles(statement_counts_sorted, n=100)[98]  # 99th percentile
    
    # High statement count analysis
    docs_over_10 = sum(1 for count in statement_counts if count > 10)
    docs_over_15 = sum(1 for count in statement_counts if count > 15)
    docs_over_20 = sum(1 for count in statement_counts if count > 20)
    docs_over_30 = sum(1 for count in statement_counts if count > 30)
    
    # Print comprehensive analysis
    print(f"\n" + "="*70)
    print(f"STATEMENT DISTRIBUTION ANALYSIS")
    print(f"="*70)
    
    print(f"BASIC STATISTICS:")
    print(f"  Total documents: {total_docs:,}")
    print(f"  Total statements: {total_statements:,}")
    print(f"  Mean statements per doc: {mean:.2f}")
    print(f"  Median statements per doc: {median:.1f}")
    print(f"  Mode (most common): {mode_count} statements ({mode_frequency:,} docs)")
    print(f"  Minimum: {min(statement_counts)}")
    print(f"  Maximum: {max(statement_counts)}")
    
    print(f"\nPERCENTILE BREAKDOWN:")
    print(f"  25th percentile (Q1): {q1:.1f}")
    print(f"  50th percentile (Median): {median:.1f}")
    print(f"  75th percentile (Q3): {q3:.1f}")
    print(f"  90th percentile: {p90:.1f}")
    print(f"  95th percentile: {p95:.1f}")
    print(f"  99th percentile: {p99:.1f}")
    
    print(f"\nHIGH STATEMENT COUNT ANALYSIS:")
    print(f"  Documents with >10 statements: {docs_over_10:,} ({docs_over_10/total_docs*100:.1f}%)")
    print(f"  Documents with >15 statements: {docs_over_15:,} ({docs_over_15/total_docs*100:.1f}%)")
    print(f"  Documents with >20 statements: {docs_over_20:,} ({docs_over_20/total_docs*100:.1f}%)")
    print(f"  Documents with >30 statements: {docs_over_30:,} ({docs_over_30/total_docs*100:.1f}%)")
    
    # Detailed distribution
    print(f"\nDETAILED DISTRIBUTION (statement count: number of documents):")
    
    # Show distribution for 1-20 statements
    for i in range(1, 21):
        count = sum(1 for sc in statement_counts if sc == i)
        if count > 0:
            percentage = (count / total_docs) * 100
            print(f"  {i:2d} statements: {count:4,} docs ({percentage:4.1f}%)")
    
    # Group higher counts
    ranges = [
        (21, 25, "21-25"),
        (26, 30, "26-30"), 
        (31, 40, "31-40"),
        (41, 50, "41-50"),
        (51, 100, "51-100")
    ]
    
    for min_val, max_val, label in ranges:
        count = sum(1 for sc in statement_counts if min_val <= sc <= max_val)
        if count > 0:
            percentage = (count / total_docs) * 100
            print(f"  {label:>2s} statements: {count:4,} docs ({percentage:4.1f}%)")
    
    # Show the most extreme cases
    print(f"\nTOP 10 DOCUMENTS BY STATEMENT COUNT:")
    docs_with_counts = [(doc['doc_id'], doc['source'], doc['year'], doc['total_statements'], doc['target_count']) 
                        for doc in data]
    docs_sorted = sorted(docs_with_counts, key=lambda x: x[3], reverse=True)
    
    for i, (doc_id, source, year, stmt_count, target_count) in enumerate(docs_sorted[:10]):
        print(f"  {i+1:2d}. {doc_id} ({source} {year}): {stmt_count} statements, {target_count} targets")
    
    # Strategy recommendations
    print(f"\n" + "="*70)
    print(f"STRATEGY RECOMMENDATIONS:")
    print(f"="*70)
    
    if docs_over_10 < 100:
        print(f"🟢 MANAGEABLE: Only {docs_over_10} documents have >10 statements")
        print(f"   → Strategy: Can handle these documents as-is or with light filtering")
    elif docs_over_10 < 500:
        print(f"🟡 MODERATE: {docs_over_10} documents have >10 statements") 
        print(f"   → Strategy: Consider capping at 15-20 statements per document")
    else:
        print(f"🔴 CHALLENGING: {docs_over_10} documents have >10 statements")
        print(f"   → Strategy: Need systematic approach to handle high-count documents")
    
    if docs_over_20 > 50:
        print(f"   → Consider implementing statement sampling within documents >20 statements")
    
    if max(statement_counts) > 40:
        print(f"   → Documents with >40 statements may need special handling for model context")
    
    # Context window considerations
    avg_chars_per_statement = 800  # Rough estimate
    max_chars = max(statement_counts) * avg_chars_per_statement
    print(f"\nCONTEXT CONSIDERATIONS:")
    print(f"  Estimated max document size: ~{max_chars:,} characters")
    print(f"  This is {'within' if max_chars < 100000 else 'beyond'} typical model context limits")

if __name__ == "__main__":
    file_path = r"C:\Users\spatt\Desktop\namingnames\docanalysis\data\finetune_03.jsonl"
    analyze_statement_distribution(file_path)