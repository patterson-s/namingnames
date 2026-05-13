import requests
from typing import Dict, Any, List, Optional, Union
import dspy
import json


class CohereClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.cohere.com/v2/chat"
        
    def call_api(self, messages: List[Dict], **kwargs) -> Optional[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = self._build_payload(messages, **kwargs)
        
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=180
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                try:
                    error_detail = e.response.json()
                    print(f"Error details: {error_detail}")
                except:
                    print(f"Response text: {e.response.text}")
            return None
    
    def _build_payload(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        payload = {
            "model": kwargs.get("model", "command-a-03-2025"),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 8000),
            "temperature": kwargs.get("temperature", 0.3),
            "p": kwargs.get("p", 0.75),
            "k": kwargs.get("k", 0),
            "frequency_penalty": kwargs.get("frequency_penalty", 0.0),
            "presence_penalty": kwargs.get("presence_penalty", 0.0),
            "seed": kwargs.get("seed", None),
            "stop_sequences": kwargs.get("stop_sequences", []),
        }
        
        return {k: v for k, v in payload.items() if v is not None and v != []}
    
    def extract_response_text(self, response: Dict[str, Any]) -> Optional[str]:
        if not response or 'message' not in response:
            return None
            
        content = response['message'].get('content')
        if isinstance(content, list) and len(content) > 0 and 'text' in content[0]:
            return content[0]['text']
        elif isinstance(content, str):
            return content
        
        return str(content) if content else None


class CohereDSPyClient:
    """Simple Cohere client that bypasses DSPy's LM interface for direct usage"""
    
    def __init__(self, api_key: str, model: str = "command-a-03-2025", **kwargs):
        self.client = CohereClient(api_key)
        self.model = model
        self.kwargs = {
            "max_tokens": 8000,
            "temperature": 0.3,
            **kwargs
        }
    
    def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate a response from the Cohere API"""
        messages = [{"role": "user", "content": prompt}]
        
        response = self.client.call_api(
            messages=messages,
            model=self.model,
            **{**self.kwargs, **kwargs}
        )
        
        if response:
            text = self.client.extract_response_text(response)
            return text if text else ""
        
        return ""