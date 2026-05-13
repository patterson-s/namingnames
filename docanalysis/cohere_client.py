#!/usr/bin/env python3

import os
import requests
from typing import Optional, Dict, Any, List


class CohereClient:
    def __init__(self):
        self.api_key = os.getenv('COHERE_API_KEY')
        if not self.api_key:
            raise ValueError("COHERE_API_KEY environment variable not set")
        
        self.base_url = "https://api.cohere.com/v2/chat"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def generate(self, 
                 user_prompt: str,
                 system_prompt: Optional[str] = None,
                 model: str = "command-a-03-2025",
                 temperature: float = 0.3,  # Lower for more consistent JSON output
                 max_tokens: int = 8000,
                 p: float = 0.75,
                 k: int = 0,
                 frequency_penalty: float = 0.0,
                 presence_penalty: float = 0.0,
                 seed: Optional[int] = None) -> str:
        """Generate text using Cohere Command-A v2 API"""
        
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user", 
            "content": user_prompt
        })
        
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            p=p,
            k=k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed
        )
        
        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json=payload,
                timeout=180
            )
            response.raise_for_status()
            result = response.json()
            return self._extract_response_text(result)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f" Status: {e.response.status_code}"
                try:
                    error_detail = e.response.json()
                    error_msg += f" Details: {error_detail}"
                except:
                    error_msg += f" Response: {e.response.text}"
            raise Exception(error_msg)
    
    def _build_payload(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """Build API payload with non-null values"""
        payload = {
            "model": kwargs.get("model", "command-a-03-2025"),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 8000),
            "temperature": kwargs.get("temperature", 0.3),
            "p": kwargs.get("p", 0.75),
            "k": kwargs.get("k", 0),
            "frequency_penalty": kwargs.get("frequency_penalty", 0.0),
            "presence_penalty": kwargs.get("presence_penalty", 0.0),
        }
        
        # Add seed if provided
        if kwargs.get("seed") is not None:
            payload["seed"] = kwargs["seed"]
        
        # Remove None values
        return {k: v for k, v in payload.items() if v is not None}
    
    def _extract_response_text(self, response: Dict[str, Any]) -> str:
        """Extract text from API response"""
        if not response or 'message' not in response:
            raise Exception("Invalid response format")
            
        content = response['message'].get('content')
        if isinstance(content, list) and len(content) > 0 and 'text' in content[0]:
            return content[0]['text']
        elif isinstance(content, str):
            return content
        
        return str(content) if content else "No response text found"