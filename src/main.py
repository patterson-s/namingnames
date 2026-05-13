import os
import sys
import click
from dotenv import load_dotenv

# Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cohere_client import CohereDSPyClient
from data_loader import DataLoader
from dspy_modules import DiplomaticAnalysisPipeline
from report_generator import ReportGenerator


@click.command()
@click.option('--input-path', required=True, help='Path to CSV file or directory containing speech files')
@click.option('--output-dir', default='./output', help='Directory for output files')
@click.option('--api-key', help='Cohere API key (or set COHERE_API_KEY env var)')
@click.option('--batch-size', default=5, type=int, help='Number of speeches per batch')
@click.option('--max-speeches', type=int, help='Maximum number of speeches to analyze (for testing)')
def main(input_path: str, output_dir: str, api_key: str, batch_size: int, max_speeches: int):
    """
    Analyze diplomatic speeches to identify characterization patterns.
    
    Input formats supported:
    - CSV file: should contain 'iso', 'year', and 'text' columns
    - Directory with files: filename should be {country}_{year}.txt
    - JSON files: should contain 'content', 'country', and 'year' fields
    """
    load_dotenv()
    
    api_key = api_key or os.getenv('COHERE_API_KEY')
    if not api_key:
        click.echo("Error: Cohere API key required. Set COHERE_API_KEY env var or use --api-key")
        return
    
    if not os.path.exists(input_path):
        click.echo(f"Error: Input path {input_path} does not exist")
        return
    
    click.echo(f"Loading speeches from {input_path}...")
    data_loader = DataLoader(input_path)
    speech_batches = data_loader.load_speeches(batch_size=batch_size, max_speeches=max_speeches)
    
    if not speech_batches:
        click.echo("Error: No speeches found in input")
        return
    
    total_speeches = sum(len(batch) for batch in speech_batches)
    click.echo(f"Found {total_speeches} speeches in {len(speech_batches)} batches")
    
    # Show sample of speeches
    sample_speeches = []
    for batch in speech_batches[:2]:  # Show first 2 batches
        sample_speeches.extend(batch)
    
    for i, speech in enumerate(sample_speeches[:10]):  # Show max 10 examples
        click.echo(f"  - {speech.country} ({speech.year})")
    
    if total_speeches > 10:
        click.echo(f"  ... and {total_speeches - 10} more")
    
    click.echo(f"\nBatch size: {batch_size} speeches per batch")
    
    click.echo("\nInitializing analysis pipeline...")
    cohere_client = CohereDSPyClient(api_key)
    pipeline = DiplomaticAnalysisPipeline(cohere_client)
    
    click.echo("Starting analysis...")
    typology_result = pipeline.analyze_speech_batches(speech_batches)
    full_conversation = pipeline.get_full_conversation()
    
    click.echo("Generating reports...")
    report_generator = ReportGenerator(output_dir)
    report_generator.generate_reports(typology_result, full_conversation, total_speeches)
    
    click.echo(f"\nAnalysis complete! Check {output_dir} for results:")
    click.echo(f"  - typology_report.md: Summary of characterization patterns")
    click.echo(f"  - full_conversation.md: Complete analysis conversation")


if __name__ == '__main__':
    main()