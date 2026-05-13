import dspy
import logging
import json
from datetime import datetime
from pathlib import Path
from data_converter import load_labeled_examples, validate_examples
from simple_metrics import classification_accuracy, METRICS
from dspy_adapter import DSPyAggressorClassifier

def setup_logging():
    """Setup logging for optimization run"""
    log_file = f"results/bootstrap_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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

def run_baseline_evaluation(classifier, examples, metrics_to_use=None):
    """Evaluate baseline performance before optimization"""
    if metrics_to_use is None:
        metrics_to_use = ['classification_accuracy', 'format_compliance', 'combined_success']
    
    logging.info(f"Running baseline evaluation on {len(examples)} examples...")
    
    results = {metric: [] for metric in metrics_to_use}
    detailed_results = []
    
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
    
    return summary, detailed_results

def run_bootstrap_optimization(classifier, examples):
    """Run BootstrapFewShot optimization"""
    
    logging.info("Starting BootstrapFewShot optimization...")
    
    # Configure optimization
    config = {
        'max_bootstrapped_demos': 6,  # Conservative to control cost
        'max_labeled_demos': 2,       # Use some of your labeled examples directly
        'metric': classification_accuracy
    }
    
    logging.info(f"Optimization config: {config}")
    
    try:
        # Create optimizer
        optimizer = dspy.BootstrapFewShot(**config)
        
        # Run optimization
        logging.info("Running optimization (this may take 5-10 minutes)...")
        optimized_classifier = optimizer.compile(classifier, trainset=examples)
        
        logging.info("Optimization completed successfully!")
        return optimized_classifier
        
    except Exception as e:
        logging.error(f"Optimization failed: {e}")
        raise

def save_results(baseline_results, optimized_results, baseline_detailed, optimized_detailed):
    """Save optimization results"""
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create results directory
    Path("results").mkdir(exist_ok=True)
    Path("optimized_models").mkdir(exist_ok=True)
    
    # Prepare summary results
    results_summary = {
        'timestamp': timestamp,
        'optimization_type': 'BootstrapFewShot',
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
    summary_file = f"results/bootstrap_summary_{timestamp}.json"
    with open(summary_file, 'w') as f:
        json.dump(results_summary, f, indent=2)
    
    # Save detailed results
    detailed_file = f"results/bootstrap_detailed_{timestamp}.json"
    with open(detailed_file, 'w') as f:
        json.dump({
            'baseline_detailed': baseline_detailed,
            'optimized_detailed': optimized_detailed
        }, f, indent=2)
    
    logging.info(f"Results saved to {summary_file} and {detailed_file}")
    return summary_file, detailed_file

def main():
    """Main optimization workflow"""
    
    # Setup
    log_file = setup_logging()
    logging.info("Starting BootstrapFewShot optimization workflow")
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
        logging.info("=" * 50)
        logging.info("BASELINE EVALUATION")
        logging.info("=" * 50)
        
        baseline_results, baseline_detailed = run_baseline_evaluation(baseline_classifier, examples)
        
        logging.info("Baseline Results:")
        for metric, stats in baseline_results.items():
            logging.info(f"  {metric}: {stats['percentage']:.1f}% ({stats['count_success']}/{stats['total']})")
        
        # Optimization
        logging.info("=" * 50)
        logging.info("OPTIMIZATION")
        logging.info("=" * 50)
        
        optimized_classifier = run_bootstrap_optimization(baseline_classifier, examples)
        
        # Save optimized model
        Path("optimized_models").mkdir(exist_ok=True)  # Ensure directory exists
        model_file = f"optimized_models/bootstrap_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        optimized_classifier.save(model_file)
        logging.info(f"Optimized model saved to: {model_file}")
        
        # Evaluate optimized model
        logging.info("=" * 50)
        logging.info("OPTIMIZED EVALUATION")
        logging.info("=" * 50)
        
        optimized_results, optimized_detailed = run_baseline_evaluation(optimized_classifier, examples)
        
        logging.info("Optimized Results:")
        for metric, stats in optimized_results.items():
            logging.info(f"  {metric}: {stats['percentage']:.1f}% ({stats['count_success']}/{stats['total']})")
        
        # Show improvements
        logging.info("=" * 50)
        logging.info("IMPROVEMENT SUMMARY")
        logging.info("=" * 50)
        
        for metric in baseline_results:
            baseline_pct = baseline_results[metric]['percentage']
            optimized_pct = optimized_results[metric]['percentage']
            improvement = optimized_pct - baseline_pct
            
            logging.info(f"{metric}:")
            logging.info(f"  Baseline: {baseline_pct:.1f}%")
            logging.info(f"  Optimized: {optimized_pct:.1f}%")
            logging.info(f"  Improvement: {improvement:+.1f} percentage points")
        
        # Save results
        summary_file, detailed_file = save_results(
            baseline_results, optimized_results, 
            baseline_detailed, optimized_detailed
        )
        
        logging.info("=" * 50)
        logging.info("OPTIMIZATION COMPLETE")
        logging.info("=" * 50)
        logging.info(f"Summary: {summary_file}")
        logging.info(f"Details: {detailed_file}")
        logging.info(f"Model: {model_file}")
        
    except Exception as e:
        logging.error(f"Optimization workflow failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()