import argparse
import logging
from pathlib import Path
from typing import Set
from data_loader import load_ner_data, group_by_year, filter_by_years
from dspy_processor import DSPyClassificationProcessor
import json

def setup_logging(log_file: Path):
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

def parse_years(year_str: str) -> Set[int]:
    years = set()
    for part in year_str.split(","):
        if ":" in part:
            start, end = map(int, part.split(":"))
            years.update(range(start, end + 1))
        else:
            years.add(int(part))
    return years

def save_results(results, output_file: Path):
    """Save results in JSONL format"""
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in results:
            f.write(json.dumps(item) + '\n')

def main():
    parser = argparse.ArgumentParser(description="DSPy Aggressor Classification")
    parser.add_argument("--input", type=Path, required=True, help="Input NER JSON file")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--years", required=True, help="Years to process (e.g., 1950:1960 or 1950,1955,1960)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for processing")
    
    args = parser.parse_args()
    
    # Setup
    args.output.mkdir(parents=True, exist_ok=True)
    setup_logging(args.output / "dspy_processing.log")
    
    logging.info(f"Starting DSPy processing:")
    logging.info(f"Input: {args.input}")
    logging.info(f"Output: {args.output}")
    logging.info(f"Years: {args.years}")
    
    try:
        # Load and filter data
        years_to_process = parse_years(args.years)
        all_items = load_ner_data(args.input)
        filtered_items = filter_by_years(all_items, years_to_process)
        grouped_data = group_by_year(filtered_items)
        
        logging.info(f"Loaded {len(all_items)} total items")
        logging.info(f"Filtered to {len(filtered_items)} items for specified years")
        logging.info(f"Years available: {sorted(grouped_data.keys())}")
        
        # Initialize processor
        processor = DSPyClassificationProcessor()
        
        # Process each year
        for year in sorted(grouped_data.keys()):
            year_items = grouped_data[year]
            logging.info(f"Processing year {year} ({len(year_items)} items)")
            
            # Process in batches
            all_results = []
            for i in range(0, len(year_items), args.batch_size):
                batch = year_items[i:i + args.batch_size]
                batch_id = i // args.batch_size + 1
                
                results = processor.process_batch(batch, year, batch_id)
                all_results.extend(results)
            
            # Save year results
            output_file = args.output / f"dspy_results_{year}.jsonl"
            save_results(all_results, output_file)
            
            positive_count = sum(1 for r in all_results if r.get('classification') == '1')
            logging.info(f"Year {year} completed: {len(all_results)} processed, {positive_count} positive classifications")
        
        logging.info("All processing completed successfully!")
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()