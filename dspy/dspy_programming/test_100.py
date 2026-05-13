import logging
import json
import random
from pathlib import Path
from data_loader import load_ner_data
from raw_processor import RawDSPyProcessor

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

def test_100_examples():
    """Test Raw DSPy processor on 100 random examples"""
    print("=" * 60)
    print("TESTING 100 RANDOM EXAMPLES WITH RAW DSPY PROCESSOR")
    print("=" * 60)
    
    # Load real data
    data_path = Path("../../data/chunks_ner.json")
    all_items = load_ner_data(data_path)
    
    if len(all_items) < 100:
        print(f"Warning: Only {len(all_items)} items available, using all of them")
        test_items = all_items
    else:
        # Select 100 random items
        random.seed(42)  # For reproducibility
        test_items = random.sample(all_items, 10)
    
    print(f"Testing {len(test_items)} items...")
    print(f"This will take approximately {len(test_items) * 3 / 60:.1f} minutes")
    print()
    
    # Create output directory
    output_dir = Path("./test_outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Process the batch
    processor = RawDSPyProcessor()
    results = processor.process_batch(test_items, year=9999, batch_id=1)

    if results:
        first_result = results[0]
        print("\n=== FIRST EXAMPLE DEBUG ===")
        print("INPUT TEXT:", first_result['text'][:200] + "...")
        print("TARGET:", first_result['target'])
        print("FULL MODEL RESPONSE:")
        print(first_result['full_response'])
        print("=== END DEBUG ===\n")
    
    # Save results
    output_file = output_dir / "raw_dspy_100_examples.jsonl"
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')
    
    # Calculate statistics
    positive_classifications = sum(1 for r in results if r['classification'] == '1')
    total_processed = len(results)
    success_rate = (total_processed / len(test_items)) * 100
    
    print(f"\nFINAL RESULTS:")
    print("=" * 40)
    print(f"Items attempted: {len(test_items)}")
    print(f"Items successfully processed: {total_processed}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Positive classifications: {positive_classifications}")
    print(f"Negative classifications: {total_processed - positive_classifications}")
    print(f"Positive rate: {positive_classifications/total_processed*100:.1f}%")
    print(f"Results saved to: {output_file}")
    
    # Show sample results
    print(f"\nSample processed items:")
    print("-" * 40)
    for i, result in enumerate(results[:10]):
        print(f"{i+1:2d}. {result['source_country']} -> {result['target']} ({result['year']}): "
              f"Class={result['classification']}")
    
    # Show positive classification examples
    positive_results = [r for r in results if r['classification'] == '1']
    if positive_results:
        print(f"\nPositive classification examples:")
        print("-" * 40)
        for i, result in enumerate(positive_results[:5]):
            print(f"{i+1}. {result['source_country']} -> {result['target']} ({result['year']})")
            print(f"   Victims: {result['victims']}")
            print(f"   Reasoning: {result['reasoning'][:80]}...")
            print()
    
    print(f"Full results available in: {output_file}")
    return results

if __name__ == "__main__":
    setup_logging()
    test_100_examples()