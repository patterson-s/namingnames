#!/usr/bin/env python3

import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path
from queue import Queue
from typing import List, Dict, Any

from config import config, RUN_CONFIGS
from neon_db import get_conn
from progress_manager import ProgressManager
from cohere_worker import CohereWorker
from batch_saver import BatchManager


class ProductionRunner:
    def __init__(self, run_id: str, num_workers: int = config.DEFAULT_WORKERS):
        self.run_id = run_id
        self.run_config = RUN_CONFIGS[run_id]
        self.num_workers = min(num_workers, config.MAX_WORKERS)
        self.progress_manager = ProgressManager(run_id)
        self.work_queue: Queue = Queue()
        self.workers: List[CohereWorker] = []
        self.worker_threads: List[threading.Thread] = []
        self.running = True
        self.monitor_thread = None
        self.countries: Dict[str, str] = {}

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\n[{self.run_id}] Received signal {signum}. Shutting down gracefully...")
        self.shutdown()

    def load_countries(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT iso3, name FROM countries")
                self.countries = {row["iso3"]: row["name"] for row in cur.fetchall()}
        print(f"[{self.run_id}] Loaded {len(self.countries)} country names")

    def load_work_items(self) -> List[Dict[str, Any]]:
        print(f"[{self.run_id}] Loading work items from {self.run_config.work_items_file}...")
        items = []
        with open(self.run_config.work_items_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
        print(f"[{self.run_id}] Loaded {len(items)} work items")
        return items

    def prepare_work_queue(self, items: List[Dict[str, Any]]) -> int:
        all_ids = {item["work_id"] for item in items}
        self.progress_manager.set_total_items(len(all_ids))
        remaining_ids = self.progress_manager.get_remaining_work_ids(all_ids)
        remaining_items = [item for item in items if item["work_id"] in remaining_ids]

        for item in remaining_items:
            self.work_queue.put(item)

        print(f"[{self.run_id}] Work queue prepared: {len(remaining_items)} items to process")
        stats = self.progress_manager.get_progress_stats()
        if stats["completed"] > 0:
            print(f"[{self.run_id}] Resuming: {stats['completed']} already completed, {stats['failed']} failed")
        return len(remaining_items)

    def start_workers(self):
        print(f"[{self.run_id}] Starting {self.num_workers} workers...")
        for i in range(self.num_workers):
            worker = CohereWorker(
                worker_id=i + 1,
                run_config=self.run_config,
                progress_manager=self.progress_manager,
                work_queue=self.work_queue,
                countries=self.countries,
            )
            thread = threading.Thread(target=worker.run, name=f"{self.run_id}-Worker-{i + 1}")
            self.workers.append(worker)
            self.worker_threads.append(thread)
            thread.start()
        print(f"[{self.run_id}] All {self.num_workers} workers started")

    def start_monitor(self):
        def monitor():
            while self.running:
                try:
                    self.progress_manager.display_progress()
                    self.progress_manager.save_progress()
                    time.sleep(config.PROGRESS_UPDATE_INTERVAL)
                except Exception as e:
                    print(f"[{self.run_id}] Monitor error: {e}")

        self.monitor_thread = threading.Thread(target=monitor, name=f"{self.run_id}-Monitor")
        self.monitor_thread.start()

    def shutdown(self):
        if not self.running:
            return
        print(f"\n[{self.run_id}] Shutting down...")
        self.running = False

        for worker in self.workers:
            worker.stop()
        for _ in self.workers:
            self.work_queue.put(None)
        for thread in self.worker_threads:
            thread.join(timeout=30)

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

        self.progress_manager.save_progress()
        print(f"[{self.run_id}] Shutdown complete")

    def wait_for_completion(self) -> bool:
        try:
            while self.running:
                if self.work_queue.empty():
                    time.sleep(2)
                    if self.work_queue.empty():
                        break
                time.sleep(1)

            for worker in self.workers:
                worker.stop()
            for _ in self.workers:
                self.work_queue.put(None)
            for thread in self.worker_threads:
                thread.join()

            self.running = False
            if self.monitor_thread:
                self.monitor_thread.join()
            return True
        except KeyboardInterrupt:
            print(f"\n[{self.run_id}] Interrupted by user")
            return False

    def print_final_summary(self):
        stats = self.progress_manager.get_progress_stats()
        batch_summary = BatchManager.get_batch_summary(self.run_id)

        print("\n" + "=" * 70)
        print(f"[{self.run_id}] PROCESSING COMPLETE")
        print("=" * 70)
        print(f"Total items: {stats['total']}")
        print(f"Successfully processed: {stats['completed']}")
        print(f"Failed: {stats['failed']}")
        if stats["total"] > 0:
            print(f"Success rate: {(stats['completed'] / stats['total'] * 100):.1f}%")
        print(f"Processing time: {stats['elapsed_minutes']:.1f} minutes")
        print(f"Batch files: {batch_summary['total_batch_files']}, total results: {batch_summary['total_results']}")

    def run(self):
        try:
            print(f"[{self.run_id}] Validating configuration...")
            config.validate_config(self.run_id)
            config.ensure_directories(self.run_id)

            self.load_countries()
            items = self.load_work_items()
            remaining_count = self.prepare_work_queue(items)

            if remaining_count == 0:
                print(f"[{self.run_id}] All items already processed!")
                self.print_final_summary()
                return True

            self.start_workers()
            self.start_monitor()

            print(f"\n[{self.run_id}] Processing {remaining_count} items with {self.num_workers} workers...")
            print("Press Ctrl+C to gracefully stop\n")

            completed = self.wait_for_completion()
            self.print_final_summary()
            return completed
        except KeyboardInterrupt:
            print(f"\n[{self.run_id}] Interrupted by user")
            return False
        except Exception as e:
            print(f"[{self.run_id}] Fatal error: {e}")
            return False
        finally:
            self.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Prompt execution runner for Naming Names coding schemes")
    parser.add_argument("--run_id", required=True, choices=list(RUN_CONFIGS.keys()))
    parser.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS)
    parser.add_argument("--validate-batches", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.validate_batches:
        validation = BatchManager.validate_batches(args.run_id)
        print(f"Total files: {validation['total_files']}")
        print(f"Valid files: {validation['valid_files']}")
        print(f"Invalid files: {validation['invalid_files']}")
        for error in validation["errors"][:5]:
            print(f"  {error['file']}: {error['error']}")
        return

    if args.summary:
        summary = BatchManager.get_batch_summary(args.run_id)
        print(f"Total batch files: {summary['total_batch_files']}")
        print(f"Total results: {summary['total_results']}")
        return

    if args.workers < 1 or args.workers > config.MAX_WORKERS:
        print(f"Number of workers must be between 1 and {config.MAX_WORKERS}")
        sys.exit(1)

    runner = ProductionRunner(run_id=args.run_id, num_workers=args.workers)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
