#!/usr/bin/env python3

import json
import re
import time
from queue import Queue, Empty
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import cohere
from config import config, RunConfig
from batch_saver import BatchSaver

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class CohereWorker:
    def __init__(
        self,
        worker_id: int,
        run_config: RunConfig,
        progress_manager,
        work_queue: Queue,
        countries: Dict[str, str],
    ):
        self.worker_id = worker_id
        self.run_config = run_config
        self.progress_manager = progress_manager
        self.work_queue = work_queue
        self.countries = countries
        self.batch_saver = BatchSaver(run_config.run_id, worker_id)
        self.running = True

        self.cohere_client = cohere.ClientV2(api_key=config.COHERE_API_KEY)
        self.system_prompt = run_config.system_prompt_file.read_text(encoding="utf-8").strip()
        self.user_prompt_template = run_config.user_prompt_template_file.read_text(encoding="utf-8").strip()

        print(f"[{run_config.run_id}] Worker {self.worker_id}: initialized (model={run_config.model_id})")

    def _format_user_prompt(self, item: Dict[str, Any]) -> str:
        fields = dict(item)
        fields["source_iso3"] = item["source"]
        fields["source_name"] = self.countries.get(item["source"], item["source"])
        if "target" in item:
            fields["target_iso3"] = item["target"]
            fields["target_name"] = self.countries.get(item["target"], item["target"])
        return self.user_prompt_template.format(**fields)

    def _call_cohere_api(self, user_prompt: str) -> Optional[str]:
        last_error = None
        for attempt in range(config.MAX_RETRIES + 1):
            try:
                response = self.cohere_client.chat(
                    model=self.run_config.model_id,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=self.run_config.max_tokens,
                )
                content = response.message.content
                if isinstance(content, list):
                    return "".join(block.text for block in content if getattr(block, "text", None))
                return content
            except Exception as e:
                last_error = e
                if attempt < config.MAX_RETRIES:
                    delay = config.RETRY_DELAY
                    if config.EXPONENTIAL_BACKOFF:
                        delay *= 2**attempt
                    print(
                        f"[{self.run_config.run_id}] Worker {self.worker_id}: API call attempt "
                        f"{attempt + 1} failed: {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    print(
                        f"[{self.run_config.run_id}] Worker {self.worker_id}: API call failed after "
                        f"{config.MAX_RETRIES + 1} attempts: {last_error}"
                    )
        return None

    def _parse_response(self, response_text: str) -> Tuple[Optional[dict], bool]:
        try:
            return json.loads(response_text.strip()), False
        except json.JSONDecodeError:
            pass

        match = JSON_BLOCK_RE.search(response_text)
        if match:
            try:
                return json.loads(match.group(0)), False
            except json.JSONDecodeError:
                pass

        return None, True

    def _process_item(self, item: Dict[str, Any]) -> bool:
        work_id = item["work_id"]
        try:
            user_prompt = self._format_user_prompt(item)
            response_text = self._call_cohere_api(user_prompt)

            if response_text is None:
                self.progress_manager.mark_failed(
                    work_id,
                    self.worker_id,
                    {"error_type": "api_failure", "message": "Failed after all retry attempts"},
                )
                return False

            parsed_response, malformed = self._parse_response(response_text)

            result = {
                "work_id": work_id,
                "run_id": self.run_config.run_id,
                "scheme": self.run_config.scheme,
                "item": item,
                "parsed_response": parsed_response,
                "malformed": malformed,
                "full_response": response_text,
                "processing_timestamp": datetime.now().isoformat(),
                "worker_id": self.worker_id,
            }
            self.batch_saver.add_result(result)
            self.progress_manager.mark_completed(work_id, self.worker_id)
            return True

        except Exception as e:
            self.progress_manager.mark_failed(
                work_id, self.worker_id, {"error_type": "processing_error", "message": str(e)}
            )
            print(f"[{self.run_config.run_id}] Worker {self.worker_id}: unexpected error on {work_id}: {e}")
            return False

    def run(self):
        print(f"[{self.run_config.run_id}] Worker {self.worker_id}: starting")
        processed_count = 0
        try:
            while self.running:
                try:
                    item = self.work_queue.get(timeout=1.0)
                    if item is None:
                        break

                    self._process_item(item)
                    processed_count += 1
                    if processed_count % 10 == 0:
                        print(f"[{self.run_config.run_id}] Worker {self.worker_id}: processed {processed_count}")

                    self.work_queue.task_done()
                except Empty:
                    continue
                except Exception as e:
                    print(f"[{self.run_config.run_id}] Worker {self.worker_id}: error in main loop: {e}")
                    continue
        finally:
            self.batch_saver.flush()
            print(f"[{self.run_config.run_id}] Worker {self.worker_id}: finished, processed {processed_count} total")

    def stop(self):
        self.running = False

    def get_stats(self) -> Dict[str, Any]:
        return {"worker_id": self.worker_id, "running": self.running, "batch_stats": self.batch_saver.get_stats()}
