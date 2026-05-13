#!/usr/bin/env python3

import json
import threading
import time
import signal
import sys
from queue import Queue
from typing import List, Dict, Any
from datetime import datetime
import argparse
from pathlib import Path

from config import config
from progress_manager import ProgressManager
from cohere_worker import CohereWorker
from batch_saver import BatchManager

class ProductionRunner:
    def __init__(self, num_workers: int = config.DEFAULT_WORKERS):
        self.num_workers = min(num_workers, config.MAX_WORKERS)
        self.progress_manager = ProgressManager()
        self.work_queue = Queue()
        self.workers: List[CohereWorker] = []
        self.worker_threads: List[threading.Thread] = []
        self.running = True
        self.monitor_thread = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C and other termination signals"""
        print(f"\n🛑 Received signal {signum}. Initiating graceful shutdown...")
        self.shutdown()
    
    def load_input_data(self) -> List[Dict[str, Any]]:
        """Load documents from input file"""
        print(f"📂 Loading input data from {config.INPUT_FILE}...")
        
        documents = []
        with open(config.INPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            documents = data if isinstance(data, list) else [data]
        
        print(f"✅ Loaded {len(documents)} documents")
        return documents
    
    def prepare_work_queue(self, documents: List[Dict[str, Any]]):
        """Prepare work queue with remaining documents"""
        # Get all document IDs
        all_doc_ids = {doc['doc_id'] for doc in documents}
        
        # Set total count in progress manager
        self.progress_manager.set_total_documents(len(all_doc_ids))
        
        # Get remaining document IDs
        remaining_doc_ids = self.progress_manager.get_remaining_doc_ids(all_doc_ids)
        
        # Add remaining documents to queue
        remaining_docs = [doc for doc in documents if doc['doc_id'] in remaining_doc_ids]
        
        for document in remaining_docs:
            self.work_queue.put(document)
        
        print(f"📋 Work queue prepared: {len(remaining_docs)} documents to process")
        
        # Show initial progress
        stats = self.progress_manager.get_progress_stats()
        if stats['completed'] > 0:
            print(f"📊 Resuming from previous session: {stats['completed']} already completed, "
                  f"{stats['failed']} failed")
        
        return len(remaining_docs)
    
    def start_workers(self):
        """Start worker threads"""
        print(f"🚀 Starting {self.num_workers} workers...")
        
        for i in range(self.num_workers):
            worker = CohereWorker(
                worker_id=i + 1,
                progress_manager=self.progress_manager,
                work_queue=self.work_queue
            )
            
            thread = threading.Thread(
                target=worker.run,
                name=f"Worker-{i + 1}"
            )
            
            self.workers.append(worker)
            self.worker_threads.append(thread)
            thread.start()
        
        print(f"✅ All {self.num_workers} workers started")
    
    def start_monitor(self):
        """Start progress monitoring thread"""
        def monitor():
            while self.running:
                try:
                    self.progress_manager.display_progress()
                    self.progress_manager.save_progress()
                    time.sleep(config.PROGRESS_UPDATE_INTERVAL)
                except Exception as e:
                    print(f"⚠️ Monitor error: {e}")
        
        self.monitor_thread = threading.Thread(target=monitor, name="Monitor")
        self.monitor_thread.start()
    
    def shutdown(self):
        """Graceful shutdown of all components"""
        if not self.running:
            return
        
        print(f"\n🔄 Shutting down...")
        self.running = False
        
        # Stop workers
        print(f"⏹️ Stopping {len(self.workers)} workers...")
        for worker in self.workers:
            worker.stop()
        
        # Add poison pills to queue to wake up workers
        for _ in self.workers:
            self.work_queue.put(None)
        
        # Wait for workers to finish current tasks
        print(f"⌛ Waiting for workers to finish current tasks...")
        for thread in self.worker_threads:
            thread.join(timeout=30)  # Wait up to 30 seconds per worker
        
        # Stop monitor
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        # Final progress save
        self.progress_manager.save_progress()
        
        print(f"✅ Shutdown complete")
    
    def wait_for_completion(self):
        """Wait for all work to complete"""
        try:
            while self.running:
                # Check if queue is empty (with timeout to allow Ctrl+C)
                if self.work_queue.empty():
                    # Wait a bit for any in-flight work to complete
                    time.sleep(2)
                    if self.work_queue.empty():
                        break
                time.sleep(1)
            
            # Stop workers gracefully
            for worker in self.workers:
                worker.stop()
            
            # Add poison pills
            for _ in self.workers:
                self.work_queue.put(None)
            
            # Wait for all workers to finish
            for thread in self.worker_threads:
                thread.join()
            
            # Stop monitoring
            self.running = False
            if self.monitor_thread:
                self.monitor_thread.join()
            
            return True
            
        except KeyboardInterrupt:
            print(f"\n⚠️ Interrupted by user")
            return False
    
    def print_final_summary(self):
        """Print final processing summary"""
        stats = self.progress_manager.get_progress_stats()
        batch_summary = BatchManager.get_batch_summary()
        
        print(f"\n" + "="*70)
        print(f"🎉 PROCESSING COMPLETE")
        print(f"="*70)
        print(f"Total documents: {stats['total']}")
        print(f"Successfully processed: {stats['completed']}")
        print(f"Failed: {stats['failed']}")
        print(f"Success rate: {(stats['completed'] / stats['total'] * 100):.1f}%")
        print(f"Processing time: {stats['elapsed_minutes']:.1f} minutes")
        print(f"Average rate: {stats['rate_per_minute']:.1f} docs/minute")
        
        print(f"\nBATCH FILES CREATED:")
        print(f"Total batch files: {batch_summary['total_batch_files']}")
        print(f"Total results saved: {batch_summary['total_results']}")
        
        if batch_summary['worker_stats']:
            print(f"\nWORKER PERFORMANCE:")
            for worker_id, worker_stats in batch_summary['worker_stats'].items():
                print(f"  Worker {worker_id}: {worker_stats['results']} results "
                      f"in {worker_stats['files']} batch files")
        
        print(f"\nOUTPUT LOCATION:")
        print(f"Batch files: {config.BATCH_DIR}")
        print(f"Progress file: {config.PROGRESS_FILE}")
        if stats['failed'] > 0:
            print(f"Failed documents log: {config.FAILED_DOCS_FILE}")
        
        if batch_summary['total_batch_files'] > 0:
            print(f"\n💡 Next steps:")
            print(f"  1. Review any failed documents in the log file")
            print(f"  2. Use merger.py to combine batch files if needed")
            print(f"  3. Validate results and proceed with analysis")
    
    def run(self):
        """Main execution method"""
        try:
            # Validate configuration
            print(f"🔧 Validating configuration...")
            config.validate_config()
            config.ensure_directories()
            
            # Load input data
            documents = self.load_input_data()
            
            # Prepare work queue
            remaining_count = self.prepare_work_queue(documents)
            
            if remaining_count == 0:
                print(f"✅ All documents already processed!")
                self.print_final_summary()
                return
            
            # Start workers
            self.start_workers()
            
            # Start monitoring
            self.start_monitor()
            
            print(f"\n🎯 Processing {remaining_count} documents with {self.num_workers} workers...")
            print(f"Press Ctrl+C to gracefully stop processing\n")
            
            # Wait for completion or interruption
            completed = self.wait_for_completion()
            
            # Print final summary
            self.print_final_summary()
            
            return completed
            
        except KeyboardInterrupt:
            print(f"\n⚠️ Interrupted by user")
            return False
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            return False
        finally:
            self.shutdown()

def main():
    parser = argparse.ArgumentParser(description="Production deployment for diplomatic analysis")
    parser.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS,
                        help=f"Number of workers (1-{config.MAX_WORKERS})")
    parser.add_argument("--validate-batches", action="store_true",
                        help="Validate existing batch files and exit")
    parser.add_argument("--summary", action="store_true",
                        help="Show summary of existing results and exit")
    
    args = parser.parse_args()
    
    # Handle utility commands
    if args.validate_batches:
        print("🔍 Validating batch files...")
        validation = BatchManager.validate_batches()
        print(f"Total files: {validation['total_files']}")
        print(f"Valid files: {validation['valid_files']}")
        print(f"Invalid files: {validation['invalid_files']}")
        if validation['errors']:
            print("Errors found:")
            for error in validation['errors'][:5]:  # Show first 5 errors
                print(f"  {error['file']}: {error['error']}")
        return
    
    if args.summary:
        print("📊 Batch summary:")
        summary = BatchManager.get_batch_summary()
        print(f"Total batch files: {summary['total_batch_files']}")
        print(f"Total results: {summary['total_results']}")
        if summary['worker_stats']:
            for worker_id, stats in summary['worker_stats'].items():
                print(f"  Worker {worker_id}: {stats['results']} results")
        return
    
    # Validate workers argument
    if args.workers < 1 or args.workers > config.MAX_WORKERS:
        print(f"❌ Number of workers must be between 1 and {config.MAX_WORKERS}")
        sys.exit(1)
    
    # Run production processing
    runner = ProductionRunner(num_workers=args.workers)
    success = runner.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()