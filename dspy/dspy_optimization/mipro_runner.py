import dspy
import logging
import json
from datetime import datetime
from pathlib import Path
from data_converter import load_labeled_examples, validate_examples
from simple_metrics import format_compliance, classification_accuracy, combined_success, METRICS
from dspy_adapter import DSPyAggressorClassifier

def setup_logging():
    """Setup logging for MIPROv2 optimization run"""
    log_file = f"results/mipro_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    Path("results").mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file

def run_evaluation(classifier, examples, label=""):
    """Evaluate classifier performance"""
    metrics_to_use = ['classification_accuracy', 'format_compliance', 'combined_success']
    
    logging.info(f"Running {label} evaluation on {len(examples)} examples...")
    
    results = {metric: [] for metric in metrics_to_use}
    detailed_results = []
    format_examples = []  # Track examples for format analysis
    
    for i, example in enumerate(examples):
        try:
            # Run classifier on this example
            pred = classifier(text=example.text, target=example.target)
            
            # Evaluate with each metric
            example_results = {'example_index': i}
            for metric_name in metrics_to_use:
                if metric_name in METRICS:
                    score = METRICS[metric_name](example, pred, trace=None)
                    results[metric_name].append(score)
                    example_results[metric_name] = score
            
            # Store format examples for analysis
            if hasattr(pred, 'full_response'):
                format_examples.append({
                    'index': i,
                    'target': example.target,
                    'has_thinking': '{THINKING}' in pred.full_response.upper(),
                    'has_response': '{RESPONSE}' in pred.full_response.upper(),
                    'response_preview': pred.full_response[:200] + "..." if len(pred.full_response) > 200 else pred.full_response
                })
            
            # Store detailed results
            example_results.update({
                'text_preview': example.text[:100] + "...",
                'target': example.target,
                'expected_classification': example.correct_classification,
                'actual_classification': getattr(pred, 'classification', 'N/A'),
                'reasoning': getattr(pred, 'reasoning', 'N/A')[:100] + "..."
            })
            detailed_results.append(example_results)
            
            if (i + 1) % 10 == 0:
                logging.info(f"Evaluated {i + 1}/{len(examples)} examples")
                
        except Exception as e:
            logging.error(f"Error evaluating example {i}: {e}")
            for metric_name in metrics_to_use:
                results[metric_name].append(0.0)
    
    # Calculate summary statistics
    summary = {}
    for metric_name, scores in results.items():
        if scores:
            summary[metric_name] = {
                'mean': sum(scores) / len(scores),
                'count_success': sum(1 for s in scores if s > 0.5),
                'total': len(scores),
                'percentage': (sum(1 for s in scores if s > 0.5) / len(scores)) * 100
            }
        else:
            summary[metric_name] = {'mean': 0.0, 'count_success': 0, 'total': 0, 'percentage': 0.0}
    
    # Log format analysis
    if format_examples:
        thinking_count = sum(1 for ex in format_examples if ex['has_thinking'])
        response_count = sum(1 for ex in format_examples if ex['has_response'])
        logging.info(f"Format Analysis - {label}:")
        logging.info(f"  Examples with {{THINKING}}: {thinking_count}/{len(format_examples)}")
        logging.info(f"  Examples with {{RESPONSE}}: {response_count}/{len(format_examples)}")
        
        # Show some examples of format failures
        if thinking_count == 0:
            logging.info("  Sample responses (no proper format found):")
            for i, ex in enumerate(format_examples[:3]):
                logging.info(f"    {i+1}. {ex['response_preview']}")
    
    return summary, detailed_results

def run_mipro_optimization(classifier, examples):
    """Run MIPROv2 optimization focused on format compliance"""
    
    logging.info("Starting MIPROv2 optimization...")
    
    # Split data for MIPROv2 (it wants trainset and valset)
    # Use 70% for training, 30% for validation
    split_point = int(len(examples) * 0.7)
    trainset = examples[:split_point]
    valset = examples[split_point:]
    
    logging.info(f"Training set: {len(trainset)} examples")
    logging.info(f"Validation set: {len(valset)} examples")
    
    # Configure MIPROv2 with format compliance as primary metric
    config = {
        'metric': combined_success,  # Target both format AND classification
        'auto': 'light',  # Start with light mode to control cost
        'num_threads': 1  # Conservative to avoid rate limits
    }
    
    logging.info(f"MIPROv2 config: {config}")
    logging.info(f"Will use {len(trainset)} training examples and {len(valset)} validation examples")
    
    try:
        # Create optimizer
        logging.info("Creating MIPROv2 optimizer...")
        optimizer = dspy.MIPROv2(**config)
        
        # Run optimization
        logging.info("Running MIPROv2 optimization...")
        logging.info("This may take 20-40 minutes and will try many instruction variations...")
        logging.info("The optimizer will focus on finding instructions that improve format compliance...")
        
        optimized_classifier = optimizer.compile(classifier, trainset=trainset, valset=valset)
        
        logging.info("MIPROv2 optimization completed successfully!")
        return optimized_classifier
        
    except Exception as e:
        logging.error(f"MIPROv2 optimization failed: {e}")
        raise

def save_mipro_results(baseline_results, optimized_results, baseline_detailed, optimized_detailed):
    """Save MIPROv2 optimization results"""
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create results directory
    Path("results").mkdir(exist_ok=True)
    Path("optimized_models").mkdir(exist_ok=True)
    
    # Prepare summary results
    results_summary = {
        'timestamp': timestamp,
        'optimization_type': 'MIPROv2',
        'baseline_performance': baseline_results,
        'optimized_performance': optimized_results,
        'improvement': {}
    }
    
    # Calculate improvements
    for metric in baseline_results:
        baseline_pct = baseline_results[metric]['percentage']
        optimized_pct = optimized_results[metric]['percentage']
        improvement = optimized_pct - baseline_pct
        results_summary['improvement'][metric] = {
            'baseline_percentage': baseline_pct,
            'optimized_percentage': optimized_pct,
            'improvement_points': improvement
        }
    
    # Save summary
    summary_file = f"results/mipro_summary_{timestamp}.json"
    with open(summary_file, 'w') as f:
        json.dump(results_summary, f, indent=2)
    
    # Save detailed results
    detailed_file = f"results/mipro_detailed_{timestamp}.json"
    with open(detailed_file, 'w') as f:
        json.dump({
            'baseline_detailed': baseline_detailed,
            'optimized_detailed': optimized_detailed
        }, f, indent=2)
    
    logging.info(f"Results saved to {summary_file} and {detailed_file}")
    return summary_file, detailed_file

def main():
    """Main MIPROv2 optimization workflow"""
    
    # Setup
    log_file = setup_logging()
    logging.info("Starting MIPROv2 optimization workflow")
    logging.info("Goal: Improve format compliance while maintaining classification accuracy")
    logging.info(f"Log file: {log_file}")
    
    try:
        # Load data
        data_file = "../dspy_evaluation/r2/gold_standard_examples_20250714_151304.jsonl"
        logging.info(f"Loading examples from: {data_file}")
        
        examples = load_labeled_examples(data_file)
        summary = validate_examples(examples)
        
        logging.info("Data summary:")
        for key, value in summary.items():
            logging.info(f"  {key}: {value}")
        
        if not summary['valid']:
            logging.error("Invalid data, stopping")
            return
        
        # Setup DSPy and classifier
        from config import setup_dspy_cohere
        setup_dspy_cohere()
        
        baseline_classifier = DSPyAggressorClassifier()
        
        # Baseline evaluation
        logging.info("=" * 60)
        logging.info("BASELINE EVALUATION (PRE-MIPRO)")
        logging.info("=" * 60)
        
        baseline_results, baseline_detailed = run_evaluation(baseline_classifier, examples, "Baseline")
        
        logging.info("Baseline Results:")
        for metric, stats in baseline_results.items():
            logging.info(f"  {metric}: {stats['percentage']:.1f}% ({stats['count_success']}/{stats['total']})")
        
        # MIPROv2 Optimization
        logging.info("=" * 60)
        logging.info("MIPROV2 OPTIMIZATION")
        logging.info("=" * 60)
        
        optimized_classifier = run_mipro_optimization(baseline_classifier, examples)
        
        # Save optimized model
        Path("optimized_models").mkdir(exist_ok=True)
        model_file = f"optimized_models/mipro_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        optimized_classifier.save(model_file)
        logging.info(f"Optimized model saved to: {model_file}")
        
        # Evaluate optimized model
        logging.info("=" * 60)
        logging.info("OPTIMIZED EVALUATION (POST-MIPRO)")
        logging.info("=" * 60)
        
        optimized_results, optimized_detailed = run_evaluation(optimized_classifier, examples, "Optimized")
        
        logging.info("Optimized Results:")
        for metric, stats in optimized_results.items():
            logging.info(f"  {metric}: {stats['percentage']:.1f}% ({stats['count_success']}/{stats['total']})")
        
        # Show improvements
        logging.info("=" * 60)
        logging.info("MIPROV2 IMPROVEMENT SUMMARY")
        logging.info("=" * 60)
        
        for metric in baseline_results:
            baseline_pct = baseline_results[metric]['percentage']
            optimized_pct = optimized_results[metric]['percentage']
            improvement = optimized_pct - baseline_pct
            
            logging.info(f"{metric}:")
            logging.info(f"  Baseline: {baseline_pct:.1f}%")
            logging.info(f"  Optimized: {optimized_pct:.1f}%")
            logging.info(f"  Improvement: {improvement:+.1f} percentage points")
            
            # Special analysis for format compliance
            if metric == 'format_compliance' and improvement > 0:
                logging.info(f"  🎉 FORMAT COMPLIANCE BREAKTHROUGH! 🎉")
            elif metric == 'format_compliance' and improvement == 0:
                logging.info(f"  😞 Format compliance still needs work")
        
        # Save results
        summary_file, detailed_file = save_mipro_results(
            baseline_results, optimized_results, 
            baseline_detailed, optimized_detailed
        )
        
        logging.info("=" * 60)
        logging.info("MIPROV2 OPTIMIZATION COMPLETE")
        logging.info("=" * 60)
        logging.info(f"Summary: {summary_file}")
        logging.info(f"Details: {detailed_file}")
        logging.info(f"Model: {model_file}")
        logging.info(f"Log: {log_file}")
        
        # Final recommendation
        final_format_pct = optimized_results['format_compliance']['percentage']
        final_classification_pct = optimized_results['classification_accuracy']['percentage']
        
        if final_format_pct > 20:
            logging.info("🎉 SUCCESS: Significant format compliance improvement!")
            logging.info("   Ready for large-scale processing")
        elif final_format_pct > 5:
            logging.info("📈 PARTIAL SUCCESS: Some format improvement")
            logging.info("   Consider additional optimization or accept current state")
        else:
            logging.info("🤔 FORMAT CHALLENGE: MIPROv2 couldn't fix format compliance")
            logging.info("   This suggests the issue may be model capability rather than instructions")
            logging.info("   Options: Try different model, accept fallback parsing, or manual format fixes")
        
    except Exception as e:
        logging.error(f"MIPROv2 optimization workflow failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()