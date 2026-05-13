#!/usr/bin/env python3

import json
import time
import threading
from queue import Queue, Empty
from typing import Dict, Any, Optional
from datetime import datetime
import cohere
from config import config
from batch_saver import BatchSaver

class CohereWorker:
    def __init__(self, worker_id: int, progress_manager, work_queue: Queue):
        self.worker_id = worker_id
        self.progress_manager = progress_manager
        self.work_queue = work_queue
        self.batch_saver = BatchSaver(worker_id)
        self.cohere_client = None
        self.system_prompt = ""
        self.running = True
        
        # Initialize Cohere client
        self._init_cohere_client()
        self._load_system_prompt()
    
    def _init_cohere_client(self):
        """Initialize Cohere client"""
        try:
            self.cohere_client = cohere.ClientV2(api_key=config.COHERE_API_KEY)
            print(f"✅ Worker {self.worker_id}: Cohere client initialized")
        except Exception as e:
            print(f"❌ Worker {self.worker_id}: Failed to initialize Cohere client: {e}")
            raise
    
    def _load_system_prompt(self):
        """Load system prompt from file"""
        try:
            with open(config.SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read().strip()
            print(f"✅ Worker {self.worker_id}: System prompt loaded ({len(self.system_prompt)} chars)")
        except Exception as e:
            print(f"❌ Worker {self.worker_id}: Failed to load system prompt: {e}")
            raise
    
    def _format_user_prompt(self, document: Dict[str, Any]) -> str:
        """Format document as user prompt (raw JSON)"""
        return json.dumps(document, indent=2, ensure_ascii=False)
    
    def _call_cohere_api(self, user_prompt: str) -> Optional[str]:
        """Make API call to Cohere with retries"""
        last_error = None
        
        for attempt in range(config.MAX_RETRIES + 1):
            try:
                response = self.cohere_client.chat(
                    model=config.COHERE_MODEL_ID,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                # Extract response text
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    if isinstance(response.message.content, list):
                        # Handle list of content blocks
                        content_text = ""
                        for content_block in response.message.content:
                            if hasattr(content_block, 'text'):
                                content_text += content_block.text
                        return content_text
                    else:
                        return response.message.content
                else:
                    raise ValueError("Unexpected response format from Cohere API")
                
            except Exception as e:
                last_error = e
                if attempt < config.MAX_RETRIES:
                    delay = config.RETRY_DELAY
                    if config.EXPONENTIAL_BACKOFF:
                        delay *= (2 ** attempt)
                    
                    print(f"⚠️ Worker {self.worker_id}: API call attempt {attempt + 1} failed: {e}. "
                          f"Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    print(f"❌ Worker {self.worker_id}: API call failed after {config.MAX_RETRIES + 1} attempts")
        
        return None
    
    def _process_document(self, document: Dict[str, Any]) -> bool:
        """Process a single document"""
        doc_id = document.get('doc_id', 'unknown')
        
        try:
            # Format user prompt
            user_prompt = self._format_user_prompt(document)
            
            # Call Cohere API
            response_text = self._call_cohere_api(user_prompt)
            
            if response_text is None:
                # API call failed after all retries
                error_info = {
                    'error_type': 'api_failure',
                    'message': 'Failed after all retry attempts',
                    'attempts': config.MAX_RETRIES + 1
                }
                self.progress_manager.mark_failed(doc_id, self.worker_id, error_info)
                return False
            
            # Create result record
            result = {
                'doc_id': doc_id,
                'source': document.get('source'),
                'year': document.get('year'),
                'targets': document.get('targets'),
                'input_data': document,
                'model_response': response_text,
                'processing_timestamp': datetime.now().isoformat(),
                'worker_id': self.worker_id
            }
            
            # Save result
            self.batch_saver.add_result(result)
            
            # Mark as completed
            self.progress_manager.mark_completed(doc_id, self.worker_id)
            
            return True
            
        except Exception as e:
            # Unexpected error during processing
            error_info = {
                'error_type': 'processing_error',
                'message': str(e),
                'document_id': doc_id
            }
            self.progress_manager.mark_failed(doc_id, self.worker_id, error_info)
            print(f"❌ Worker {self.worker_id}: Unexpected error processing {doc_id}: {e}")
            return False
    
    def run(self):
        """Main worker loop"""
        print(f"🚀 Worker {self.worker_id}: Starting processing")
        
        processed_count = 0
        
        try:
            while self.running:
                try:
                    # Get next document from queue (with timeout to allow graceful shutdown)
                    document = self.work_queue.get(timeout=1.0)
                    
                    if document is None:  # Poison pill to stop worker
                        break
                    
                    # Process document
                    success = self._process_document(document)
                    processed_count += 1
                    
                    if success and processed_count % 10 == 0:
                        print(f"📈 Worker {self.worker_id}: Processed {processed_count} documents")
                    
                    # Mark task as done
                    self.work_queue.task_done()
                    
                except Empty:
                    # Timeout - continue loop to check if we should stop
                    continue
                    
                except Exception as e:
                    print(f"❌ Worker {self.worker_id}: Unexpected error in main loop: {e}")
                    # Continue processing other documents
                    continue
        
        finally:
            # Flush any remaining results
            self.batch_saver.flush()
            print(f"🏁 Worker {self.worker_id}: Finished. Processed {processed_count} documents total.")
    
    def stop(self):
        """Signal worker to stop"""
        self.running = False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics"""
        batch_stats = self.batch_saver.get_stats()
        return {
            'worker_id': self.worker_id,
            'running': self.running,
            'batch_stats': batch_stats
        }