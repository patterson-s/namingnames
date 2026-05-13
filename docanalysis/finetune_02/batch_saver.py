#!/usr/bin/env python3

import json
import threading
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from config import config

class BatchSaver:
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.lock = threading.Lock()
        self.batch_buffer: List[Dict[str, Any]] = []
        self.batch_counter = 1
        self.total_saved = 0
    
    def add_result(self, result: Dict[str, Any]):
        """Add result to batch buffer"""
        with self.lock:
            # Add metadata
            result_with_meta = {
                'doc_id': result.get('doc_id'),
                'worker_id': self.worker_id,
                'timestamp': datetime.now().isoformat(),
                'result': result
            }
            
            self.batch_buffer.append(result_with_meta)
            
            # Save batch if buffer is full
            if len(self.batch_buffer) >= config.BATCH_SIZE:
                self._save_batch()
    
    def _save_batch(self):
        """Save current batch buffer to file"""
        if not self.batch_buffer:
            return
        
        # Generate batch filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_filename = f"worker_{self.worker_id}_batch_{self.batch_counter:03d}_{timestamp}.jsonl"
        batch_filepath = config.BATCH_DIR / batch_filename
        
        try:
            # Write batch to file
            with open(batch_filepath, 'w', encoding='utf-8') as f:
                for result in self.batch_buffer:
                    f.write(json.dumps(result) + '\n')
            
            # Update counters
            saved_count = len(self.batch_buffer)
            self.total_saved += saved_count
            self.batch_counter += 1
            
            print(f"💾 Worker {self.worker_id}: Saved batch {self.batch_counter-1} "
                  f"({saved_count} results) to {batch_filename}")
            
            # Clear buffer
            self.batch_buffer.clear()
            
        except Exception as e:
            print(f"❌ Worker {self.worker_id}: Failed to save batch {batch_filename}: {e}")
            # Keep results in buffer for retry
    
    def flush(self):
        """Force save any remaining results in buffer"""
        with self.lock:
            if self.batch_buffer:
                self._save_batch()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get saver statistics"""
        with self.lock:
            return {
                'worker_id': self.worker_id,
                'total_saved': self.total_saved,
                'current_batch': self.batch_counter,
                'buffer_size': len(self.batch_buffer)
            }

class BatchManager:
    """Global batch manager for coordination"""
    
    @staticmethod
    def get_all_batch_files() -> List[Path]:
        """Get all batch files in the batch directory"""
        return list(config.BATCH_DIR.glob("*.jsonl"))
    
    @staticmethod
    def count_total_results() -> int:
        """Count total results across all batch files"""
        total = 0
        for batch_file in BatchManager.get_all_batch_files():
            try:
                with open(batch_file, 'r', encoding='utf-8') as f:
                    total += sum(1 for line in f if line.strip())
            except Exception as e:
                print(f"⚠️ Warning: Could not read batch file {batch_file}: {e}")
        return total
    
    @staticmethod
    def get_batch_summary() -> Dict[str, Any]:
        """Get summary of all batch files"""
        batch_files = BatchManager.get_all_batch_files()
        total_results = BatchManager.count_total_results()
        
        worker_stats = {}
        for batch_file in batch_files:
            # Parse worker ID from filename
            try:
                filename = batch_file.name
                if filename.startswith("worker_"):
                    worker_id = int(filename.split("_")[1])
                    if worker_id not in worker_stats:
                        worker_stats[worker_id] = {'files': 0, 'results': 0}
                    worker_stats[worker_id]['files'] += 1
                    
                    # Count results in this file
                    with open(batch_file, 'r', encoding='utf-8') as f:
                        file_results = sum(1 for line in f if line.strip())
                        worker_stats[worker_id]['results'] += file_results
                        
            except Exception as e:
                print(f"⚠️ Warning: Could not parse batch file {batch_file}: {e}")
        
        return {
            'total_batch_files': len(batch_files),
            'total_results': total_results,
            'worker_stats': worker_stats,
            'oldest_batch': min(batch_files, key=lambda f: f.stat().st_mtime) if batch_files else None,
            'newest_batch': max(batch_files, key=lambda f: f.stat().st_mtime) if batch_files else None
        }
    
    @staticmethod
    def validate_batches() -> Dict[str, Any]:
        """Validate all batch files for integrity"""
        batch_files = BatchManager.get_all_batch_files()
        validation_results = {
            'total_files': len(batch_files),
            'valid_files': 0,
            'invalid_files': 0,
            'errors': []
        }
        
        for batch_file in batch_files:
            try:
                with open(batch_file, 'r', encoding='utf-8') as f:
                    line_count = 0
                    for line_num, line in enumerate(f, 1):
                        if line.strip():
                            line_count += 1
                            # Validate JSON structure
                            result = json.loads(line)
                            if 'doc_id' not in result:
                                raise ValueError(f"Missing doc_id in line {line_num}")
                            if 'result' not in result:
                                raise ValueError(f"Missing result in line {line_num}")
                
                validation_results['valid_files'] += 1
                
            except Exception as e:
                validation_results['invalid_files'] += 1
                validation_results['errors'].append({
                    'file': str(batch_file),
                    'error': str(e)
                })
        
        return validation_results