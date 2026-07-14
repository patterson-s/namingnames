#!/usr/bin/env python3

import json
import threading
from typing import Set, Dict, Any
from datetime import datetime
from config import config


class ProgressManager:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.lock = threading.Lock()
        self.completed_items: Set[str] = set()
        self.failed_items: Set[str] = set()
        self.worker_progress: Dict[int, Dict] = {}
        self.start_time = datetime.now()
        self.total_items = 0

        self._load_existing_progress()

    def _load_existing_progress(self):
        print(f"[{self.run_id}] Scanning for existing progress...")

        batch_dir = config.dirs_for_run(self.run_id)["batch_dir"]
        for batch_file in batch_dir.glob("*.jsonl"):
            try:
                with open(batch_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            result = json.loads(line)
                            if "work_id" in result:
                                self.completed_items.add(result["work_id"])
            except Exception as e:
                print(f"Warning: could not read batch file {batch_file}: {e}")

        failed_file = config.failed_items_file(self.run_id)
        if failed_file.exists():
            try:
                with open(failed_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            failed = json.loads(line)
                            if "work_id" in failed:
                                self.failed_items.add(failed["work_id"])
            except Exception as e:
                print(f"Warning: could not read failed items file: {e}")

        progress_file = config.progress_file(self.run_id)
        if progress_file.exists():
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress_data = json.load(f)
                    self.completed_items.update(progress_data.get("completed_items", []))
            except Exception as e:
                print(f"Warning: could not read progress file: {e}")

        if self.completed_items:
            print(f"[{self.run_id}] Found {len(self.completed_items)} already completed items")
        if self.failed_items:
            print(f"[{self.run_id}] Found {len(self.failed_items)} previously failed items")

    def set_total_items(self, total: int):
        self.total_items = total

    def mark_completed(self, work_id: str, worker_id: int):
        with self.lock:
            self.completed_items.add(work_id)
            self._update_worker_stats(worker_id, "completed")

    def mark_failed(self, work_id: str, worker_id: int, error_info: Dict[str, Any]):
        with self.lock:
            self.failed_items.add(work_id)
            self._update_worker_stats(worker_id, "failed")

            failed_entry = {
                "work_id": work_id,
                "worker_id": worker_id,
                "timestamp": datetime.now().isoformat(),
                "error": error_info,
            }
            try:
                with open(config.failed_items_file(self.run_id), "a", encoding="utf-8") as f:
                    f.write(json.dumps(failed_entry) + "\n")
            except Exception as e:
                print(f"Warning: could not write to failed items file: {e}")

    def _update_worker_stats(self, worker_id: int, action: str):
        if worker_id not in self.worker_progress:
            self.worker_progress[worker_id] = {
                "completed": 0,
                "failed": 0,
                "last_activity": datetime.now(),
            }
        self.worker_progress[worker_id][action] += 1
        self.worker_progress[worker_id]["last_activity"] = datetime.now()

    def get_progress_stats(self) -> Dict[str, Any]:
        with self.lock:
            completed_count = len(self.completed_items)
            failed_count = len(self.failed_items)
            processed_count = completed_count + failed_count
            remaining_count = self.total_items - processed_count

            elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
            rate = processed_count / elapsed_seconds if elapsed_seconds > 0 else 0
            eta_seconds = remaining_count / rate if rate > 0 else 0

            return {
                "total": self.total_items,
                "completed": completed_count,
                "failed": failed_count,
                "remaining": remaining_count,
                "processed": processed_count,
                "progress_percent": (processed_count / self.total_items * 100) if self.total_items > 0 else 0,
                "rate_per_minute": rate * 60,
                "eta_minutes": eta_seconds / 60,
                "elapsed_minutes": elapsed_seconds / 60,
                "worker_stats": dict(self.worker_progress),
            }

    def save_progress(self):
        try:
            with self.lock:
                worker_progress_serializable = {
                    worker_id: {
                        "completed": stats["completed"],
                        "failed": stats["failed"],
                        "last_activity": stats["last_activity"].isoformat(),
                    }
                    for worker_id, stats in self.worker_progress.items()
                }
                progress_data = {
                    "timestamp": datetime.now().isoformat(),
                    "completed_items": list(self.completed_items),
                    "failed_items": list(self.failed_items),
                    "total_items": self.total_items,
                    "worker_progress": worker_progress_serializable,
                }
            with open(config.progress_file(self.run_id), "w", encoding="utf-8") as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            print(f"Warning: could not save progress: {e}")

    def get_remaining_work_ids(self, all_work_ids: Set[str]) -> Set[str]:
        with self.lock:
            processed = self.completed_items | self.failed_items
            return all_work_ids - processed

    def display_progress(self):
        stats = self.get_progress_stats()
        print(
            f"\r[{self.run_id}] Progress: {stats['completed']}/{stats['total']} completed "
            f"({stats['progress_percent']:.1f}%) | "
            f"Rate: {stats['rate_per_minute']:.1f}/min | "
            f"ETA: {stats['eta_minutes']:.0f}m | "
            f"Failed: {stats['failed']}",
            end="",
            flush=True,
        )
        if config.SHOW_WORKER_DETAILS and stats["worker_stats"]:
            print()
            for worker_id, worker_stats in stats["worker_stats"].items():
                time_since = (datetime.now() - worker_stats["last_activity"]).total_seconds()
                status = "active" if time_since < 30 else "idle"
                print(
                    f"  Worker {worker_id}: {worker_stats['completed']} completed, "
                    f"{worker_stats['failed']} failed ({status})"
                )
