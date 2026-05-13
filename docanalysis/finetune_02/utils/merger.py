#!/usr/bin/env python3

import json
import argparse
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
import sys
import os

# Add parent directory to path to import config
sys.path.append(str(Path(__file__).parent.parent))
from config import config
from batch_saver import BatchManager

class BatchMerger:
    def __init__(self):
        self.merged_results: List[Dict[str, Any]] = []
        self.duplicate_doc_ids: set = set()
        self.stats = {
            'total_files_processed': 0,
            'total_results_found': 0,
            'duplicates_found': 0,
            'valid_results': 0,
            'errors': []
        }
    
    def merge_all_batches(self, output_file: Path, sort_by_timestamp: bool = True) -> bool:
        """Merge all batch files into a single output file"""
        print(f"🔄 Starting batch merge process...")
        
        # Get all batch files
        batch_files = BatchManager.get_all_batch_files()
        if not batch_files:
            print(f"❌ No batch files found in {config.BATCH_DIR}")
            return False
        
        print(f"📁 Found {len(batch_files)} batch files to merge")
        
        # Process each batch file
        for batch_file in batch_files:
            self._process_batch_file(batch_file)
        
        # Sort results if requested
        if sort_by_timestamp and self.merged_results:
            print(f"🔄 Sorting {len(self.merged_results)} results by timestamp...")
            self.merged_results.sort(key=lambda x: x.get('timestamp', ''))
        
        # Write merged results
        return self._write_merged_results(output_file)
    
    def _process_batch_file(self, batch_file: Path):
        """Process a single batch file"""
        try:
            self.stats['total_files_processed'] += 1
            print(f"📄 Processing {batch_file.name}...")
            
            file_results = 0
            file_duplicates = 0
            
            with open(batch_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    
                    try:
                        result = json.loads(line)
                        file_results += 1
                        self.stats['total_results_found'] += 1
                        
                        # Check for required fields
                        if 'doc_id' not in result:
                            self.stats['errors'].append(f"{batch_file.name}:{line_num} - Missing doc_id")
                            continue
                        
                        doc_id = result['doc_id']
                        
                        # Check for duplicates
                        if doc_id in self.duplicate_doc_ids:
                            self.stats['duplicates_found'] += 1
                            file_duplicates += 1
                            print(f"⚠️ Duplicate doc_id found: {doc_id} in {batch_file.name}:{line_num}")
                            continue
                        
                        # Add to results
                        self.duplicate_doc_ids.add(doc_id)
                        self.merged_results.append(result)
                        self.stats['valid_results'] += 1
                        
                    except json.JSONDecodeError as e:
                        self.stats['errors'].append(f"{batch_file.name}:{line_num} - Invalid JSON: {e}")
                        continue
            
            print(f"  ✅ {file_results} results processed ({file_duplicates} duplicates skipped)")
            
        except Exception as e:
            error_msg = f"Failed to process {batch_file.name}: {e}"
            self.stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
    
    def _write_merged_results(self, output_file: Path) -> bool:
        """Write merged results to output file"""
        try:
            print(f"💾 Writing {len(self.merged_results)} results to {output_file}...")
            
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                for result in self.merged_results:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
            
            print(f"✅ Merged results written to {output_file}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to write merged results: {e}"
            self.stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
            return False
    
    def create_analysis_ready_format(self, output_file: Path) -> bool:
        """Create analysis-ready format with just doc_id and model response"""
        try:
            print(f"🔄 Creating analysis-ready format...")
            
            analysis_results = []
            for result in self.merged_results:
                if 'result' in result and 'model_response' in result['result']:
                    analysis_result = {
                        'doc_id': result['doc_id'],
                        'source': result.get('result', {}).get('source'),
                        'year': result.get('result', {}).get('year'),
                        'targets': result.get('result', {}).get('targets'),
                        'model_response': result['result']['model_response'],
                        'processing_timestamp': result.get('timestamp')
                    }
                    analysis_results.append(analysis_result)
            
            analysis_file = output_file.parent / f"{output_file.stem}_analysis{output_file.suffix}"
            
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_results, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Analysis-ready format written to {analysis_file}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create analysis-ready format: {e}")
            return False
    
    def print_summary(self):
        """Print merge summary"""
        print(f"\n" + "="*60)
        print(f"📊 BATCH MERGE SUMMARY")
        print(f"="*60)
        print(f"Files processed: {self.stats['total_files_processed']}")
        print(f"Total results found: {self.stats['total_results_found']}")
        print(f"Duplicates found: {self.stats['duplicates_found']}")
        print(f"Valid results merged: {self.stats['valid_results']}")
        print(f"Errors encountered: {len(self.stats['errors'])}")
        
        if self.stats['errors']:
            print(f"\nERRORS:")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                print(f"  {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more errors")
        
        success_rate = (self.stats['valid_results'] / self.stats['total_results_found'] * 100) if self.stats['total_results_found'] > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")

def main():
    parser = argparse.ArgumentParser(description="Merge batch files from production run")
    parser.add_argument("--output", 
                        default=str(config.OUTPUT_DIR / f"merged_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"),
                        help="Output file path")
    parser.add_argument("--no-sort", action="store_true",
                        help="Don't sort results by timestamp")
    parser.add_argument("--analysis-format", action="store_true",
                        help="Also create analysis-ready format")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate batch files, don't merge")
    
    args = parser.parse_args()
    
    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        return False
    
    # Validation-only mode
    if args.validate_only:
        print("🔍 Validating batch files only...")
        validation = BatchManager.validate_batches()
        print(f"Total files: {validation['total_files']}")
        print(f"Valid files: {validation['valid_files']}")
        print(f"Invalid files: {validation['invalid_files']}")
        if validation['errors']:
            print("Validation errors:")
            for error in validation['errors']:
                print(f"  {error['file']}: {error['error']}")
        return validation['invalid_files'] == 0
    
    # Merge process
    merger = BatchMerger()
    output_file = Path(args.output)
    
    success = merger.merge_all_batches(
        output_file=output_file,
        sort_by_timestamp=not args.no_sort
    )
    
    if success and args.analysis_format:
        merger.create_analysis_ready_format(output_file)
    
    merger.print_summary()
    
    if success:
        print(f"\n🎉 Merge completed successfully!")
        print(f"Merged file: {output_file}")
    else:
        print(f"\n❌ Merge failed!")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)