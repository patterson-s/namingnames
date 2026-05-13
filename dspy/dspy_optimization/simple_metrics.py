import dspy
import re
import logging
from typing import Dict, Any

def classification_accuracy(example, pred, trace=None):
    """Check if classification matches ground truth"""
    try:
        expected = str(example.correct_classification)
        actual = str(getattr(pred, 'classification', ''))
        
        match = expected == actual
        
        if trace is None:  # Evaluation mode
            return 1.0 if match else 0.0
        else:  # Optimization mode (boolean for filtering)
            return match
            
    except Exception as e:
        logging.warning(f"Classification accuracy metric error: {e}")
        return 0.0

def format_compliance(example, pred, trace=None):
    """Check if output has proper {THINKING} and {RESPONSE} structure"""
    try:
        # Get the full response text
        full_response = getattr(pred, 'full_response', '') or str(pred)
        
        # Check for both {THINKING} and {RESPONSE} sections
        has_thinking = bool(re.search(r'\{THINKING\}.*?/\{THINKING\}', full_response, re.DOTALL | re.IGNORECASE))
        has_response = bool(re.search(r'\{RESPONSE\}.*?/\{RESPONSE\}', full_response, re.DOTALL | re.IGNORECASE))
        
        compliant = has_thinking and has_response
        
        if trace is None:  # Evaluation mode
            return 1.0 if compliant else 0.0
        else:  # Optimization mode (boolean for filtering)
            return compliant
            
    except Exception as e:
        logging.warning(f"Format compliance metric error: {e}")
        return 0.0

def combined_success(example, pred, trace=None):
    """Both classification correct AND format compliant"""
    try:
        classification_correct = classification_accuracy(example, pred, trace) > 0.5
        format_correct = format_compliance(example, pred, trace) > 0.5
        
        success = classification_correct and format_correct
        
        if trace is None:  # Evaluation mode
            return 1.0 if success else 0.0
        else:  # Optimization mode (boolean for filtering)
            return success
            
    except Exception as e:
        logging.warning(f"Combined success metric error: {e}")
        return 0.0

def reasoning_similarity(example, pred, trace=None):
    """Simple check if reasoning mentions key concepts from ground truth"""
    try:
        expected_reasoning = getattr(example, 'correct_reasoning', '').lower()
        actual_reasoning = getattr(pred, 'reasoning', '').lower()
        
        if not expected_reasoning or not actual_reasoning:
            return 0.0
        
        # Simple keyword overlap check
        expected_words = set(expected_reasoning.split())
        actual_words = set(actual_reasoning.split())
        
        # Remove common words
        stop_words = {'the', 'is', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        expected_words -= stop_words
        actual_words -= stop_words
        
        if not expected_words:
            return 0.0
        
        overlap = len(expected_words.intersection(actual_words))
        similarity = overlap / len(expected_words)
        
        if trace is None:  # Evaluation mode
            return similarity
        else:  # Optimization mode (boolean for filtering)
            return similarity > 0.3  # At least 30% keyword overlap
            
    except Exception as e:
        logging.warning(f"Reasoning similarity metric error: {e}")
        return 0.0

# For DSPy optimization, we want a primary metric that filters good examples
def primary_optimization_metric(example, pred, trace=None):
    """Primary metric for optimization - prioritizes classification accuracy"""
    return classification_accuracy(example, pred, trace)

# Metric definitions for easy access
METRICS = {
    'classification_accuracy': classification_accuracy,
    'format_compliance': format_compliance,
    'combined_success': combined_success,
    'reasoning_similarity': reasoning_similarity,
    'primary': primary_optimization_metric
}

def evaluate_prediction(example, pred, metrics_to_use=None):
    """Evaluate a single prediction against multiple metrics"""
    if metrics_to_use is None:
        metrics_to_use = ['classification_accuracy', 'format_compliance', 'combined_success']
    
    results = {}
    for metric_name in metrics_to_use:
        if metric_name in METRICS:
            try:
                score = METRICS[metric_name](example, pred, trace=None)
                results[metric_name] = score
            except Exception as e:
                logging.warning(f"Error evaluating {metric_name}: {e}")
                results[metric_name] = 0.0
        else:
            logging.warning(f"Unknown metric: {metric_name}")
    
    return results

if __name__ == "__main__":
    # Test metrics with mock data
    import dspy
    
    # Mock example
    example = dspy.Example(
        text="Sample text",
        target="USA",
        correct_classification="1",
        correct_reasoning="The USA is portrayed as aggressive"
    ).with_inputs('text', 'target')
    
    # Mock prediction - simulating your current output format
    class MockPrediction:
        def __init__(self):
            self.classification = "1"
            self.victims = ""
            self.reasoning = "The USA is shown as aggressive"
            self.full_response = "Some analysis without proper format"
    
    pred = MockPrediction()
    
    # Test all metrics
    results = evaluate_prediction(example, pred)
    
    print("Metric Test Results:")
    print("=" * 30)
    for metric, score in results.items():
        print(f"{metric}: {score}")