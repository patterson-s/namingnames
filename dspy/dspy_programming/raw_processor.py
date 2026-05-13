from typing import Dict, List, Any
import logging
import re
from datetime import datetime
from config import setup_dspy_cohere

class RawDSPyProcessor:
    """Simplified processor that gets raw text from DSPy without structured parsing"""
    
    def __init__(self):
        setup_dspy_cohere()
        
        # Create the full system prompt text
        self.system_prompt = """You are a diplomatic analyst hired specifically for your ability to identify aggressive or malicious state behavior in UN General Assembly speeches. Your job - and continued employment - depends on your ability to determine if states are explicitly portrayed as taking aggressive or malicious action against other entities.

Classification Criteria:
This is a binary classification task (0 or 1) with specific requirements:
1. The target state must be EXPLICITLY portrayed as taking aggressive or malicious action
2. This aggressive action must be directed against clearly identifiable entities

The classification should be "1" only if the target state is clearly portrayed as an aggressor. Otherwise, it should be "0".

Required Analysis Steps:

1. Target State Focus
   - Identify the target state in the text
   - Confirm that any discussed actions are specifically attributed to the target state
   - Note any other states/entities mentioned in relation to the target state

2. Action Analysis
   - Examine how the target state's actions are portrayed
   - Identify EXPLICIT language depicting aggressive or malicious behavior
   - Quote specific text demonstrating aggressive actions
   - Determine if aggressive action criterion is FULFILLED or NOT FULFILLED

3. Victim Identification
   - Identify entities that are explicitly portrayed as receiving aggressive actions
   - Extract direct quotes describing these entities
   - Maintain focus only on entities that are direct recipients of the target's actions

4. Final Classification
   - Review if target state is explicitly portrayed as aggressor
   - Compile list of victims from text
   - Determine final classification (0 or 1)

CRITICAL: You MUST structure your response in EXACTLY this format. Do NOT deviate from this structure:

{THINKING}
Step 1: Target State Focus
[Analysis of target state identification and attribution]

Step 2: Action Analysis  
[Analysis of how actions are portrayed, with specific quotes]

Step 3: Victim Identification
[Analysis of entities receiving aggressive actions]

Step 4: Final Classification
[Review and determination of classification]
/{THINKING}

{RESPONSE}
Classification: 0
Victims: 
Reasoning: The target state is not explicitly portrayed as taking aggressive actions against identifiable entities.
/{RESPONSE}

YOU MUST USE EXACTLY THIS FORMAT. No other format will be accepted."""

        print("=== SYSTEM PROMPT LOADED ===")
        print(self.system_prompt[-200:])  # Print last 200 chars to see the format section
        print("=== END SYSTEM PROMPT ===")

    def process_single(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            # Use raw LM call instead of DSPy modules
            lm = __import__('dspy').settings.lm
            
            user_prompt = f"""Document to analyze:
Text: {item["text"]}
Target State: {item["target"]}

Please analyze this document following the steps outlined above to determine if the target state is portrayed as an aggressor."""
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call the model directly
            response = lm(messages=messages, temperature=0.7, max_tokens=4096)
            
            # Extract the response text
            if isinstance(response, list) and len(response) > 0:
                response_text = response[0]
            elif hasattr(response, 'choices') and len(response.choices) > 0:
                response_text = response.choices[0].message.content
            else:
                response_text = str(response)
            
            logging.info(f"Raw response: {response_text[:200]}...")
            
            # Parse the response
            extracted = self._extract_from_text(response_text)
            
            if extracted:
                # Create output matching original format
                processed_result = {
                    **item,
                    "full_response": response_text,
                    "classification": str(extracted.get('classification', 0)),
                    "victims": str(extracted.get('victims', '')),
                    "reasoning": str(extracted.get('reasoning', ''))
                }
                return processed_result
            else:
                logging.error(f"Could not parse response: {response_text}")
                return None
                
        except Exception as e:
            logging.error(f"Error processing item: {str(e)}")
            return None
    
    def _extract_from_text(self, text: str) -> Dict[str, str] | None:
        """Extract structured output from text response"""
        
        # First try to extract from {RESPONSE} section
        response_match = re.search(r'\{RESPONSE\}(.*?)/\{RESPONSE\}', text, re.DOTALL | re.IGNORECASE)
        
        if response_match:
            response_content = response_match.group(1).strip()
            
            # Parse the response content
            patterns = {
                "classification": r"Classification:\s*([01])",
                "victims": r"Victims:\s*([^\n]*)",
                "reasoning": r"Reasoning:\s*([^\n]*)"
            }
            
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, response_content, re.IGNORECASE)
                if match:
                    extracted[key] = match.group(1).strip()
            
            # Ensure we have at least classification
            if 'classification' in extracted:
                return extracted
        
        # Fallback: try old XML format
        xml_patterns = {
            "classification": r"<CLASSIFICATION>([^<]+)</CLASSIFICATION>",
            "victims": r"<VICTIMS>([^<]*)</VICTIMS>", 
            "reasoning": r"<REASONING>([^<]+)</REASONING>"
        }
        
        extracted = {}
        for key, pattern in xml_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                extracted[key] = match.group(1).strip()
        
        # If we found the structured format, return it
        if 'classification' in extracted:
            return extracted
        
        # Final fallback: try to infer from the response text
        logging.info("Structured format not found, attempting fallback parsing...")
        
        lower_text = text.lower()
        
        # Determine classification based on content
        aggression_indicators = [
            "clearly portrayed as an aggressor",
            "explicitly portrayed as aggressor", 
            "portrayed as an aggressor",
            "is an aggressor",
            "aggressive behavior",
            "aggressive actions",
            "classification: 1",
            "result: 1"
        ]
        
        non_aggression_indicators = [
            "not portrayed as an aggressor",
            "no aggression",
            "classification: 0", 
            "result: 0",
            "no explicit aggression"
        ]
        
        classification = "0"  # Default to no aggression
        
        for indicator in aggression_indicators:
            if indicator in lower_text:
                classification = "1"
                break
        
        for indicator in non_aggression_indicators:
            if indicator in lower_text:
                classification = "0"
                break
        
        # Try to extract victims and reasoning from the text
        victims = ""
        reasoning = "Classification based on content analysis of the response."
        
        # Look for victim mentions
        victim_patterns = [
            r"victims?:?\s*([^\n\.]+)",
            r"against\s+([A-Z][a-zA-Z\s]+?)(?:\s+and|\.|,)",
            r"sovereignty",  # Common victim reference
        ]
        
        for pattern in victim_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                victims = match.group(1).strip() if match.lastindex else "sovereignty"
                break
        
        return {
            "classification": classification,
            "victims": victims,
            "reasoning": reasoning
        }
    
    def process_batch(self, items: List[Dict[str, Any]], year: int, batch_id: int) -> List[Dict[str, Any]]:
        results = []
        total = len(items)
        start_time = datetime.now()
        
        for i, item in enumerate(items):
            try:
                result = self.process_single(item)
                if result:
                    results.append(result)
                
                if (i + 1) % 5 == 0:  # Log every 5 items for testing
                    elapsed = datetime.now() - start_time
                    items_per_sec = (i + 1) / elapsed.total_seconds()
                    remaining_secs = (total - (i + 1)) / items_per_sec
                    
                    logging.info(
                        f"Year {year} - Batch {batch_id}: "
                        f"Processed {i+1}/{total} items "
                        f"({((i+1)/total)*100:.1f}%) - "
                        f"Est. remaining: {remaining_secs/60:.1f} minutes"
                    )
                    
            except Exception as e:
                logging.error(f"Error processing item: {str(e)}")
        
        return results