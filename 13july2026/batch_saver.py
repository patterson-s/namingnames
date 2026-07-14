#!/usr/bin/env python3

import json
import threading
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from config import config


class BatchSaver:
    def __init__(self, run_id: str, worker_id: int):
        self.run_id = run_id
        self.worker_id = worker_id
        self.lock = threading.Lock()
        self.batch_buffer: List[Dict[str, Any]] = []
        self.batch_counter = 1
        self.total_saved = 0

    def add_result(self, result: Dict[str, Any]):
        with self.lock:
            self.batch_buffer.append(result)
            if len(self.batch_buffer) >= config.BATCH_SIZE:
                self._save_batch()

    def _save_batch(self):
        if not self.batch_buffer:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_dir = config.dirs_for_run(self.run_id)["batch_dir"]
        batch_filename = f"worker_{self.worker_id}_batch_{self.batch_counter:03d}_{timestamp}.jsonl"
        batch_filepath = batch_dir / batch_filename

        try:
            with open(batch_filepath, "w", encoding="utf-8") as f:
                for result in self.batch_buffer:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")

            saved_count = len(self.batch_buffer)
            self.total_saved += saved_count
            self.batch_counter += 1
            print(f"[{self.run_id}] Worker {self.worker_id}: saved batch ({saved_count} results) -> {batch_filename}")
            self.batch_buffer.clear()
        except Exception as e:
            print(f"[{self.run_id}] Worker {self.worker_id}: failed to save batch {batch_filename}: {e}")

    def flush(self):
        with self.lock:
            if self.batch_buffer:
                self._save_batch()

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "worker_id": self.worker_id,
                "total_saved": self.total_saved,
                "current_batch": self.batch_counter,
                "buffer_size": len(self.batch_buffer),
            }


class BatchManager:
    @staticmethod
    def get_all_batch_files(run_id: str) -> List[Path]:
        return list(config.dirs_for_run(run_id)["batch_dir"].glob("*.jsonl"))

    @staticmethod
    def count_total_results(run_id: str) -> int:
        total = 0
        for batch_file in BatchManager.get_all_batch_files(run_id):
            try:
                with open(batch_file, "r", encoding="utf-8") as f:
                    total += sum(1 for line in f if line.strip())
            except Exception as e:
                print(f"Warning: could not read batch file {batch_file}: {e}")
        return total

    @staticmethod
    def get_batch_summary(run_id: str) -> Dict[str, Any]:
        batch_files = BatchManager.get_all_batch_files(run_id)
        total_results = BatchManager.count_total_results(run_id)

        worker_stats: Dict[int, Dict[str, int]] = {}
        for batch_file in batch_files:
            try:
                filename = batch_file.name
                if filename.startswith("worker_"):
                    worker_id = int(filename.split("_")[1])
                    if worker_id not in worker_stats:
                        worker_stats[worker_id] = {"files": 0, "results": 0}
                    worker_stats[worker_id]["files"] += 1
                    with open(batch_file, "r", encoding="utf-8") as f:
                        worker_stats[worker_id]["results"] += sum(1 for line in f if line.strip())
            except Exception as e:
                print(f"Warning: could not parse batch file {batch_file}: {e}")

        return {
            "total_batch_files": len(batch_files),
            "total_results": total_results,
            "worker_stats": worker_stats,
        }

    @staticmethod
    def validate_batches(run_id: str) -> Dict[str, Any]:
        batch_files = BatchManager.get_all_batch_files(run_id)
        validation_results = {"total_files": len(batch_files), "valid_files": 0, "invalid_files": 0, "errors": []}

        for batch_file in batch_files:
            try:
                with open(batch_file, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if line.strip():
                            result = json.loads(line)
                            if "work_id" not in result:
                                raise ValueError(f"Missing work_id in line {line_num}")
                validation_results["valid_files"] += 1
            except Exception as e:
                validation_results["invalid_files"] += 1
                validation_results["errors"].append({"file": str(batch_file), "error": str(e)})

        return validation_results
