#!/usr/bin/env python3

import json
import threading
import time
from typing import Set, Dict, Any
from datetime import datetime
from pathlib import Path
from config import config

class ProgressManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.completed_docs: Set[str] = set()
        self.failed_docs: Set[str] = set()
        self.worker_progress: Dict[int, Dict] = {}
        self.start_time = datetime.now()
        self.total_docs = 0
        
        # Load existing progress
        self._load_existing_progress()
    
    def _load_existing_progress(self):
        """Load progress from existing batch files and progress file"""
        print("🔍 Scanning for existing progress...")
        
        # Scan batch files for completed documents
        batch_files = list(config.BATCH_DIR.glob("*.jsonl"))
        for batch_file in batch_files:
            try:
                with open(batch_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            result = json.loads(line)
                            if 'doc_id' in result:
                                self.completed_docs.add(result['doc_id'])
            except Exception as e:
                print(f"⚠️ Warning: Could not read batch file {batch_file}: {e}")
        
        # Load failed documents
        if config.FAILED_DOCS_FILE.exists():
            try:
                with open(config.FAILED_DOCS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            failed_doc = json.loads(line)
                            if 'doc_id' in failed_doc:
                                self.failed_docs.add(failed_doc['doc_id'])
            except Exception as e:
                print(f"⚠️ Warning: Could not read failed documents file: {e}")
        
        # Load progress state if exists
        if config.PROGRESS_FILE.exists():
            try:
                with open(config.PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                    saved_completed = set(progress_data.get('completed_docs', []))
                    # Merge with batch file results (batch files are authoritative)
                    self.completed_docs.update(saved_completed)
            except Exception as e:
                print(f"⚠️ Warning: Could not read progress file: {e}")
        
        if self.completed_docs:
            print(f"✅ Found {len(self.completed_docs)} already completed documents")
        if self.failed_docs:
            print(f"❌ Found {len(self.failed_docs)} previously failed documents")
    
    def set_total_documents(self, total: int):
        """Set total number of documents to process"""
        self.total_docs = total
    
    def is_completed(self, doc_id: str) -> bool:
        """Check if document is already completed"""
        with self.lock:
            return doc_id in self.completed_docs or doc_id in self.failed_docs
    
    def mark_completed(self, doc_id: str, worker_id: int):
        """Mark document as completed"""
        with self.lock:
            self.completed_docs.add(doc_id)
            self._update_worker_stats(worker_id, 'completed')
    
    def mark_failed(self, doc_id: str, worker_id: int, error_info: Dict[str, Any]):
        """Mark document as failed and log error"""
        with self.lock:
            self.failed_docs.add(doc_id)
            self._update_worker_stats(worker_id, 'failed')
            
            # Log failed document
            failed_entry = {
                'doc_id': doc_id,
                'worker_id': worker_id,
                'timestamp': datetime.now().isoformat(),
                'error': error_info
            }
            
            try:
                with open(config.FAILED_DOCS_FILE, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(failed_entry) + '\n')
            except Exception as e:
                print(f"⚠️ Warning: Could not write to failed documents file: {e}")
    
    def _update_worker_stats(self, worker_id: int, action: str):
        """Update worker statistics"""
        if worker_id not in self.worker_progress:
            self.worker_progress[worker_id] = {
                'completed': 0,
                'failed': 0,
                'last_activity': datetime.now()
            }
        
        self.worker_progress[worker_id][action] += 1
        self.worker_progress[worker_id]['last_activity'] = datetime.now()
    
    def get_progress_stats(self) -> Dict[str, Any]:
        """Get current progress statistics"""
        with self.lock:
            completed_count = len(self.completed_docs)
            failed_count = len(self.failed_docs)
            processed_count = completed_count + failed_count
            remaining_count = self.total_docs - processed_count
            
            # Calculate rate and ETA
            elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
            rate = processed_count / elapsed_seconds if elapsed_seconds > 0 else 0
            eta_seconds = remaining_count / rate if rate > 0 else 0
            
            return {
                'total': self.total_docs,
                'completed': completed_count,
                'failed': failed_count,
                'remaining': remaining_count,
                'processed': processed_count,
                'progress_percent': (processed_count / self.total_docs * 100) if self.total_docs > 0 else 0,
                'rate_per_minute': rate * 60,
                'eta_minutes': eta_seconds / 60,
                'elapsed_minutes': elapsed_seconds / 60,
                'worker_stats': dict(self.worker_progress)
            }
    
    def save_progress(self):
        """Save current progress to file"""
        try:
            with self.lock:
                # Convert datetime objects to ISO strings for JSON serialization
                worker_progress_serializable = {}
                for worker_id, stats in self.worker_progress.items():
                    worker_progress_serializable[worker_id] = {
                        'completed': stats['completed'],
                        'failed': stats['failed'],
                        'last_activity': stats['last_activity'].isoformat()
                    }
                
                progress_data = {
                    'timestamp': datetime.now().isoformat(),
                    'completed_docs': list(self.completed_docs),
                    'failed_docs': list(self.failed_docs),
                    'total_docs': self.total_docs,
                    'worker_progress': worker_progress_serializable
                }
            
            with open(config.PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2)
                
        except Exception as e:
            print(f"⚠️ Warning: Could not save progress: {e}")
    
    def get_remaining_doc_ids(self, all_doc_ids: Set[str]) -> Set[str]:
        """Get set of document IDs that still need processing"""
        with self.lock:
            processed_docs = self.completed_docs | self.failed_docs
            return all_doc_ids - processed_docs
    
    def display_progress(self):
        """Display current progress (for monitoring thread)"""
        stats = self.get_progress_stats()
        
        print(f"\r📊 Progress: {stats['completed']}/{stats['total']} completed "
              f"({stats['progress_percent']:.1f}%) | "
              f"Rate: {stats['rate_per_minute']:.1f}/min | "
              f"ETA: {stats['eta_minutes']:.0f}m | "
              f"Failed: {stats['failed']}", end="", flush=True)
        
        if config.SHOW_WORKER_DETAILS and stats['worker_stats']:
            print()  # New line for worker details
            for worker_id, worker_stats in stats['worker_stats'].items():
                last_activity = worker_stats['last_activity']
                time_since = (datetime.now() - last_activity).total_seconds()
                status = "🟢 Active" if time_since < 30 else "🟡 Idle"
                print(f"  Worker {worker_id}: {worker_stats['completed']} completed, "
                      f"{worker_stats['failed']} failed {status}")