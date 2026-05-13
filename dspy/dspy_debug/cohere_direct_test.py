import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any
import requests
from datetime import datetime

class CohereClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.cohere.com/v2/chat"
        
    def call_api(self, messages: List[Dict], **kwargs) -> Dict[str, Any] | None:
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
            "model": kwargs.get("model", "command-r7b-12-2024"),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "p": kwargs.get("p", 0.75),
            "k": kwargs.get("k", 0),
            "frequency_penalty": kwargs.get("frequency_penalty", 0.0),
            "presence_penalty": kwargs.get("presence_penalty", 0.0),
            "seed": kwargs.get("seed", None),
            "stop_sequences": kwargs.get("stop_sequences", []),
        }
        
        return {k: v for k, v in payload.items() if v is not None and v != []}
    
    def extract_response_text(self, response: Dict[str, Any]) -> str | None:
        if not response or 'message' not in response:
            return None
            
        content = response['message'].get('content')
        if isinstance(content, list) and len(content) > 0 and 'text' in content[0]:
            return content[0]['text']
        elif isinstance(content, str):
            return content
        
        return str(content) if content else None

def load_gold_standard_examples(file_path: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Load examples from gold standard dataset"""
    examples = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if line_num >= limit:  # Limit for testing
                break
                
            try:
                data = json.loads(line.strip())
                examples.append(data)
            except json.JSONDecodeError as e:
                print(f"Skipping malformed line {line_num + 1}: {e}")
    
    print(f"Loaded {len(examples)} examples for testing")
    return examples

def create_system_prompt() -> str:
    """Create the exact system prompt from raw_processor.py"""
    return """You are a diplomatic analyst hired specifically for your ability to identify aggressive or malicious state behavior in UN General Assembly speeches. Your job - and continued employment - depends on your ability to determine if states are explicitly portrayed as taking aggressive or malicious action against other entities.

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

EXAMPLE OUTPUT FORMAT:

{THINKING}
Step 1: Target State Focus
The target state USA is mentioned in the context of arms supply to belligerents in Afghanistan.

Step 2: Action Analysis
The text states "the United States and Soviet Union to terminate supply of arms to belligerents will starve both parties." This portrays arms supply as contributing to conflict.

Step 3: Victim Identification  
Afghanistan is identified as the location where this arms supply fueled conflict.

Step 4: Final Classification
The USA is portrayed as contributing to aggression through arms supply, meeting the criteria for classification as 1.
/{THINKING}

{RESPONSE}
Classification: 1
Victims: Afghanistan
Reasoning: The United States is explicitly described as supplying arms that prolonged conflict in Afghanistan.
/{RESPONSE}

YOU MUST USE EXACTLY THIS FORMAT. No other format will be accepted."""

def analyze_format_compliance(response_text: str) -> Dict[str, Any]:
    """Analyze if response follows the required format"""
    
    # Check for {THINKING} section
    thinking_match = re.search(r'\{THINKING\}(.*?)/\{THINKING\}', response_text, re.DOTALL | re.IGNORECASE)
    has_thinking = thinking_match is not None
    thinking_content = thinking_match.group(1).strip() if thinking_match else ""
    
    # Check for {RESPONSE} section
    response_match = re.search(r'\{RESPONSE\}(.*?)/\{RESPONSE\}', response_text, re.DOTALL | re.IGNORECASE)
    has_response = response_match is not None
    response_content = response_match.group(1).strip() if response_match else ""
    
    # Extract classification, victims, reasoning from response section
    classification = ""
    victims = ""
    reasoning = ""
    
    if has_response:
        class_match = re.search(r'Classification:\s*([01])', response_content, re.IGNORECASE)
        victims_match = re.search(r'Victims:\s*([^\n]*)', response_content, re.IGNORECASE)
        reasoning_match = re.search(r'Reasoning:\s*([^\n]*)', response_content, re.IGNORECASE)
        
        if class_match:
            classification = class_match.group(1).strip()
        if victims_match:
            victims = victims_match.group(1).strip()
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
    
    return {
        'has_thinking': has_thinking,
        'has_response': has_response,
        'format_compliant': has_thinking and has_response,
        'classification': classification,
        'victims': victims,
        'reasoning': reasoning,
        'thinking_length': len(thinking_content),
        'response_length': len(response_content)
    }

def test_model(client: CohereClient, model_name: str, examples: List[Dict], max_examples: int = 5):
    """Test a specific model on examples"""
    
    print(f"\n{'='*60}")
    print(f"TESTING MODEL: {model_name}")
    print(f"{'='*60}")
    
    system_prompt = create_system_prompt()
    results = []
    
    for i, example in enumerate(examples[:max_examples]):
        print(f"\nExample {i+1}/{max_examples}")
        print(f"Target: {example['target']} | Expected: {example.get('correct_classification', 'N/A')}")
        
        user_prompt = f"""Document to analyze:
Text: {example['text']}
Target State: {example['target']}

Please analyze this document following the steps outlined above to determine if the target state is portrayed as an aggressor."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Call API
            response = client.call_api(messages, model=model_name)
            
            if response:
                response_text = client.extract_response_text(response)
                
                if response_text:
                    # Analyze format compliance
                    analysis = analyze_format_compliance(response_text)
                    
                    results.append({
                        'example_index': i,
                        'target': example['target'],
                        'expected_classification': example.get('correct_classification', 'N/A'),
                        'actual_classification': analysis['classification'],
                        'format_compliant': analysis['format_compliant'],
                        'has_thinking': analysis['has_thinking'],
                        'has_response': analysis['has_response'],
                        'reasoning': analysis['reasoning'][:100] + "..." if len(analysis['reasoning']) > 100 else analysis['reasoning'],
                        'full_response': response_text
                    })
                    
                    # Print immediate feedback
                    print(f"  Format: {'✅' if analysis['format_compliant'] else '❌'} "
                          f"(Thinking: {'✅' if analysis['has_thinking'] else '❌'}, "
                          f"Response: {'✅' if analysis['has_response'] else '❌'})")
                    print(f"  Classification: {analysis['classification']} (Expected: {example.get('correct_classification', 'N/A')})")
                    
                    if not analysis['format_compliant']:
                        print(f"  Preview: {response_text[:150]}...")
                else:
                    print("  ❌ No response text extracted")
            else:
                print("  ❌ API call failed")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    return results

def summarize_results(results: List[Dict], model_name: str):
    """Summarize test results for a model"""
    
    if not results:
        print(f"\n❌ No results for {model_name}")
        return
    
    total = len(results)
    format_compliant = sum(1 for r in results if r['format_compliant'])
    has_thinking = sum(1 for r in results if r['has_thinking'])
    has_response = sum(1 for r in results if r['has_response'])
    
    # Classification accuracy (only where we have expected values)
    classification_matches = 0
    classification_total = 0
    for r in results:
        if r['expected_classification'] != 'N/A' and r['actual_classification']:
            classification_total += 1
            if r['expected_classification'] == r['actual_classification']:
                classification_matches += 1
    
    print(f"\n{'='*40}")
    print(f"{model_name} SUMMARY")
    print(f"{'='*40}")
    print(f"Total examples tested: {total}")
    print(f"Format compliance: {format_compliant}/{total} ({format_compliant/total*100:.1f}%)")
    print(f"Has {{{'{THINKING}'}}} section: {has_thinking}/{total} ({has_thinking/total*100:.1f}%)")
    print(f"Has {{{'{RESPONSE}'}}} section: {has_response}/{total} ({has_response/total*100:.1f}%)")
    
    if classification_total > 0:
        print(f"Classification accuracy: {classification_matches}/{classification_total} ({classification_matches/classification_total*100:.1f}%)")
    
    return {
        'model': model_name,
        'total': total,
        'format_compliance': format_compliant / total * 100,
        'has_thinking': has_thinking / total * 100,
        'has_response': has_response / total * 100,
        'classification_accuracy': classification_matches / classification_total * 100 if classification_total > 0 else 0
    }

def main():
    print("COHERE MODEL COMPARISON - DIRECT API BYPASS TEST")
    print("Testing format compliance outside of DSPy framework")
    print("="*60)
    
    # Setup
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        print("❌ COHERE_API_KEY not found in environment")
        return
    
    client = CohereClient(api_key)
    
    # Load examples
    data_file = "../dspy_evaluation/r2/gold_standard_examples_20250714_151304.jsonl"
    examples = load_gold_standard_examples(data_file, limit=10)  # Test on 10 examples
    
    if not examples:
        print("❌ No examples loaded")
        return
    
    # Test both models
    models_to_test = [
        "command-r7b-12-2024",
        "command-a-03-2025"
    ]
    
    all_results = {}
    all_summaries = {}
    
    for model in models_to_test:
        print(f"\n🧪 Testing {model}...")
        results = test_model(client, model, examples, max_examples=5)
        summary = summarize_results(results, model)
        
        all_results[model] = results
        all_summaries[model] = summary
    
    # Final comparison
    print(f"\n{'='*60}")
    print("FINAL COMPARISON")
    print(f"{'='*60}")
    
    for model, summary in all_summaries.items():
        if summary:
            print(f"\n{model}:")
            print(f"  Format Compliance: {summary['format_compliance']:.1f}%")
            print(f"  Classification Accuracy: {summary['classification_accuracy']:.1f}%")
    
    # Save detailed results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"direct_api_comparison_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'models_tested': models_to_test,
            'summaries': all_summaries,
            'detailed_results': all_results
        }, f, indent=2)
    
    print(f"\n📁 Detailed results saved to: {results_file}")
    
    # Key insights
    r7b_format = all_summaries.get("command-r7b-12-2024", {}).get('format_compliance', 0)
    command_a_format = all_summaries.get("command-a-03-2025", {}).get('format_compliance', 0)
    
    print(f"\n🔍 KEY INSIGHTS:")
    if command_a_format > r7b_format + 20:
        print("✅ Command-A significantly better at following format!")
        print("   → DSPy might work better with Command-A")
    elif command_a_format > r7b_format:
        print("📈 Command-A somewhat better at following format")
        print("   → Modest improvement expected with Command-A")
    else:
        print("😞 No significant format improvement with Command-A")
        print("   → Issue likely deeper than model choice")

if __name__ == "__main__":
    main()