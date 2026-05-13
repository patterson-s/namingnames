# Diplomatic Speech Analysis System

An inductive analysis system for identifying patterns in how countries characterize themselves and other nations in diplomatic speeches.

## Overview

This system performs sequential analysis of diplomatic speeches to build typologies of self-characterization and other-characterization strategies. It uses large language models to conduct inductive analysis, building cumulative understanding across multiple speeches in configurable batches.

## Features

- Sequential speech analysis with pattern building
- Configurable batch processing (default: 5 speeches per batch)
- CSV and directory input support
- Inductive typology generation
- Conversation-style analysis that builds on previous findings
- Clean markdown output with typologies and full analysis history

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your environment:
   ```bash
   export COHERE_API_KEY=your_api_key_here
   ```

## Usage

### Basic Usage with CSV

```bash
python src/main.py --input-path /path/to/speeches.csv --output-dir ./output
```

### CSV Format

Your CSV should contain these columns:
- `iso`: Country code (e.g., "MEX", "BRA", "IND")
- `year`: Year of the speech
- `text`: Full speech content

Example CSV structure:
```csv
iso,year,text
MEX,1946,"Our presence in New York affords objective proof..."
BRA,1946,"I would first like to express to the city of New York..."
```

### Advanced Options

```bash
# Custom batch size (default: 5)
python src/main.py --input-path speeches.csv --batch-size 3

# Limit number of speeches for testing
python src/main.py --input-path speeches.csv --max-speeches 10

# Custom output directory
python src/main.py --input-path speeches.csv --output-dir ./my_results
```

### Legacy Directory Input

The system also supports directories with individual files:

**Text Files** (`.txt` or `.md`):
- Filename format: `{country}_{year}.txt` (e.g., `Mexico_1946.txt`)
- Content: Raw speech text

**JSON Files** (`.json`):
```json
{
  "content": "Speech text here...",
  "country": "Mexico",
  "year": 1946
}
```

```bash
python src/main.py --input-path /path/to/speech/directory --output-dir ./output
```

### Output

The system generates two files in the output directory:

1. **`typology_report.md`**: Clean summary with:
   - Self-characterization typology (4-6 types)
   - Other-characterization typology (4-6 types)
   - Examples and explanations
   - Key insights and patterns

2. **`full_conversation.md`**: Complete analysis showing:
   - Each speech analysis with reasoning
   - Pattern building progression across batches
   - Final synthesis process

## Example with Your Data

Given your CSV format, you can run:

```bash
python src/main.py --input-path "C:\Users\spatt\Desktop\namingnames\data\ungdc_1946-2022.csv" --output-dir ./output --batch-size 5 --max-speeches 25
```

This will:
- Load speeches from your CSV file
- Process 25 speeches total (for testing)
- Analyze them in batches of 5 speeches each
- Generate comprehensive typologies and conversation history

## Requirements

- Python 3.8+
- Cohere API key
- Input data in CSV format or supported file formats

## API Configuration

The system uses Cohere's `command-a-03-2025` model by default with these settings:
- Temperature: 0.3
- Max tokens: 4000
- Timeout: 120 seconds

## Analysis Methodology

1. **Batch Processing**: Speeches are processed in configurable batches (default: 5 per batch)
2. **Sequential Analysis**: Within each batch, speeches are analyzed one by one
3. **Pattern Building**: The system maintains conversation history across all batches
4. **Inductive Approach**: Typologies emerge from the data rather than being imposed a priori
5. **Cumulative Understanding**: Later analyses explicitly reference and build upon earlier insights

## Batch Processing Benefits

- **Memory Management**: Prevents context window overflow with large datasets
- **Progress Tracking**: Clear progress indicators across batches
- **Error Recovery**: Batch-level error handling for robust processing
- **Scalability**: Can handle large CSV files with thousands of speeches

## Project Structure

```
diplomatic-speech-analysis/
├── src/
│   ├── main.py                 # CLI entry point with batch support
│   ├── cohere_client.py        # Enhanced Cohere client with DSPy
│   ├── conversation_manager.py # Conversation history across batches
│   ├── data_loader.py          # CSV and directory loading with batching
│   ├── dspy_modules.py         # DSPy analysis modules with batch processing
│   ├── response_parser.py      # XML response parsing
│   └── report_generator.py     # Output generation
├── prompts/
│   ├── system_initialization.md   # System setup instructions
│   ├── speech_analysis.md         # Individual speech analysis prompt
│   └── typology_synthesis.md      # Final typology generation prompt
└── output/
    ├── typology_report.md          # Final summary report
    └── full_conversation.md        # Complete analysis conversation
```

## Troubleshooting

### Common Issues

**"No speeches found in input"**
- Check that your CSV has the required columns: `iso`, `year`, `text`
- Verify CSV encoding is UTF-8
- Ensure file path is correct

**"API Error" messages**
- Verify your Cohere API key is correct
- Check your internet connection
- Ensure you have sufficient API credits

**"Invalid response format" warnings**
- The system will continue analysis even with some malformed responses
- Check the full conversation file for details on any parsing issues

**Memory or performance issues**
- Reduce batch size with `--batch-size 3`
- Use `--max-speeches` to limit analysis for testing
- Check available memory for large CSV files

### Performance Notes

- Analysis time depends on speech length and number of speeches
- Typical processing: 1-2 minutes per speech
- Batch processing helps manage memory and provides progress tracking
- Large speeches (>10,000 words) may take longer or hit token limits

## Customization

### Modifying Prompts

Edit the files in the `prompts/` directory to customize the analysis approach:
- `system_initialization.md`: Core instructions and response format
- `speech_analysis.md`: Individual speech analysis template
- `typology_synthesis.md`: Final synthesis instructions

### Adjusting Model Parameters

Modify the model settings in `src/cohere_client.py`:
```python
# In CohereDSPyClient.__init__()
self.kwargs = {
    "temperature": 0.3,  # Adjust for more/less creative responses
    "max_tokens": 4000,  # Increase for longer responses
    # ... other parameters
}
```

## Contributing

This is a research tool designed for academic analysis of diplomatic texts. Contributions welcome for:
- Additional input format support
- Analysis quality improvements
- Performance optimizations
- Documentation enhancements

## License

MIT License - see LICENSE file for details.

## Citation

If you use this tool in academic research, please cite:

```
Diplomatic Speech Analysis System. (2025). 
Inductive typology generation for diplomatic characterization patterns.
```

## Contact

For questions or issues, please open a GitHub issue or contact the maintainers.