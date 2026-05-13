#!/usr/bin/env python3

import dspy
import pandas as pd
import json
import re
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import html

class TextChunker(dspy.Module):
    def __init__(
        self,
        chunk_size: int = 250,
        text_column: str = 'text',
        metadata_columns: List[str] = None,
        dropped_columns: List[str] = None,
        unit: str = 'words',
        clean_html: bool = True,
        sentence_boundary: bool = True
    ):
        super().__init__()
        self.chunk_size = chunk_size
        self.text_column = text_column
        self.metadata_columns = metadata_columns or []
        self.dropped_columns = dropped_columns or []
        self.unit = unit
        self.clean_html = clean_html
        self.sentence_boundary = sentence_boundary
        
    def _clean_text(self, text: str) -> str:
        if not isinstance(text, str):
            return str(text) if text is not None else ""
            
        if self.clean_html:
            text = html.unescape(text)
            text = re.sub(r'<[^>]+>', '', text)
            
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _split_text(self, text: str) -> List[str]:
        if self.unit == 'words':
            return text.split()
        elif self.unit == 'characters':
            return list(text)
        else:
            raise ValueError(f"Unsupported unit: {self.unit}")
    
    def _join_text(self, tokens: List[str]) -> str:
        if self.unit == 'words':
            return ' '.join(tokens)
        elif self.unit == 'characters':
            return ''.join(tokens)
    
    def _find_sentence_boundary(self, tokens: List[str], target_end: int) -> int:
        if not self.sentence_boundary or self.unit != 'words':
            return target_end
            
        sentence_endings = {'.', '!', '?', '...'}
        
        for i in range(min(target_end, len(tokens) - 1), max(0, target_end - 50), -1):
            if i < len(tokens) and any(tokens[i].endswith(ending) for ending in sentence_endings):
                return i + 1
                
        return target_end
    
    def _chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        clean_text = self._clean_text(text)
        if not clean_text:
            return []
            
        tokens = self._split_text(clean_text)
        if len(tokens) <= self.chunk_size:
            return [{
                'text': clean_text,
                'metadata': metadata,
                'chunk_index': 0,
                'total_chunks': 1,
                'start_position': 0,
                'end_position': len(tokens)
            }]
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            
            if end < len(tokens):
                end = self._find_sentence_boundary(tokens, end)
            
            chunk_tokens = tokens[start:end]
            chunk_text = self._join_text(chunk_tokens)
            
            chunk_data = {
                'text': chunk_text,
                'metadata': metadata,
                'chunk_index': chunk_index,
                'total_chunks': None,
                'start_position': start,
                'end_position': end
            }
            
            chunks.append(chunk_data)
            
            start = end
            chunk_index += 1
        
        for chunk in chunks:
            chunk['total_chunks'] = len(chunks)
            
        return chunks
    
    def _load_data(self, data: Union[str, pd.DataFrame, Dict, List]) -> pd.DataFrame:
        if isinstance(data, str):
            file_path = Path(data)
            if file_path.suffix.lower() == '.csv':
                return pd.read_csv(data)
            elif file_path.suffix.lower() == '.json':
                with open(data, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                if isinstance(json_data, list):
                    return pd.DataFrame(json_data)
                else:
                    return pd.DataFrame([json_data])
            else:
                raise ValueError(f"Unsupported file type: {file_path.suffix}")
        elif isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, (dict, list)):
            if isinstance(data, dict):
                data = [data]
            return pd.DataFrame(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
    
    def forward(self, data: Union[str, pd.DataFrame, Dict, List]) -> List[Dict[str, Any]]:
        df = self._load_data(data)
        
        if self.text_column not in df.columns:
            raise ValueError(f"Text column '{self.text_column}' not found in data")
        
        # Remove dropped columns
        df_processed = df.drop(columns=self.dropped_columns, errors='ignore')
        
        # Determine metadata columns (all columns except text column)
        available_metadata_cols = [col for col in df_processed.columns if col != self.text_column]
        
        all_chunks = []
        
        for idx, row in df_processed.iterrows():
            text_content = row[self.text_column]
            
            if pd.isna(text_content) or not str(text_content).strip():
                continue
                
            metadata = {'row_id': idx}
            for col in available_metadata_cols:
                if pd.notna(row[col]):
                    metadata[col] = row[col]
            
            row_chunks = self._chunk_text(str(text_content), metadata)
            all_chunks.extend(row_chunks)
        
        return all_chunks

def interactive_setup() -> tuple[str, str, str, List[str]]:
    print("=== Interactive Text Chunker Setup ===\n")
    
    # Get input file
    while True:
        input_file = input("Enter the path to your input file (CSV or JSON): ").strip()
        if not input_file:
            print("Please provide a file path.")
            continue
        
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"File not found: {input_file}")
            continue
        
        if input_path.suffix.lower() not in ['.csv', '.json']:
            print("File must be CSV or JSON format.")
            continue
        
        break
    
    # Load file to inspect columns
    try:
        print(f"\nLoading file: {input_file}")
        if input_path.suffix.lower() == '.csv':
            df = pd.read_csv(input_file)
        else:
            with open(input_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            if isinstance(json_data, list):
                df = pd.DataFrame(json_data)
            else:
                df = pd.DataFrame([json_data])
        
        print(f"Loaded {len(df)} rows")
        
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)
    
    # Show columns
    print(f"\nFound {len(df.columns)} columns:")
    for i, col in enumerate(df.columns, 1):
        sample_val = df[col].dropna().iloc[0] if not df[col].dropna().empty else "N/A"
        print(f"  {i:2d}. {col} (sample: {str(sample_val)[:50]}...)")
    
    # Get text column
    while True:
        text_choice = input(f"\nWhich column contains the text to chunk? (1-{len(df.columns)}): ").strip()
        try:
            text_idx = int(text_choice) - 1
            if 0 <= text_idx < len(df.columns):
                text_column = df.columns[text_idx]
                print(f"Selected text column: {text_column}")
                break
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")
    
    # Get columns to drop
    print(f"\nWhich columns should be DROPPED? (Default: keep all others as metadata)")
    print("Enter column numbers separated by commas, or press Enter to keep all:")
    
    drop_choice = input("Columns to drop: ").strip()
    dropped_columns = []
    
    if drop_choice:
        try:
            drop_indices = [int(x.strip()) - 1 for x in drop_choice.split(',')]
            dropped_columns = [df.columns[i] for i in drop_indices if 0 <= i < len(df.columns)]
            print(f"Will drop columns: {dropped_columns}")
        except (ValueError, IndexError):
            print("Invalid selection, keeping all columns as metadata")
            dropped_columns = []
    
    # Get output file
    output_file = input("\nEnter output file path (with .json or .csv extension): ").strip()
    if not output_file:
        output_file = str(input_path.with_suffix('.chunks.json'))
        print(f"Using default output: {output_file}")
    
    return input_file, output_file, text_column, dropped_columns

def print_chunk_statistics(chunks: List[Dict[str, Any]], unit: str) -> None:
    if not chunks:
        print("No chunks created.")
        return
    
    print(f"\n=== Chunking Statistics ===")
    print(f"Total chunks created: {len(chunks):,}")
    
    # Calculate chunk sizes
    chunk_sizes = []
    for chunk in chunks:
        if unit == 'words':
            size = len(chunk['text'].split())
        else:
            size = len(chunk['text'])
        chunk_sizes.append(size)
    
    if chunk_sizes:
        print(f"\nChunk size statistics ({unit}):")
        print(f"  Min size: {min(chunk_sizes):,}")
        print(f"  Max size: {max(chunk_sizes):,}")
        print(f"  Average size: {sum(chunk_sizes) / len(chunk_sizes):.1f}")
        print(f"  Median size: {sorted(chunk_sizes)[len(chunk_sizes)//2]:,}")
    
    # Metadata analysis
    if chunks:
        sample_metadata = chunks[0]['metadata']
        print(f"\nMetadata fields included: {list(sample_metadata.keys())}")
        
        # Count unique values in first few metadata fields
        metadata_stats = {}
        for key in list(sample_metadata.keys())[:3]:  # First 3 fields
            unique_values = set()
            for chunk in chunks[:1000]:  # Sample first 1000 chunks
                if key in chunk['metadata']:
                    unique_values.add(str(chunk['metadata'][key]))
            metadata_stats[key] = len(unique_values)
        
        print("\nMetadata diversity (sample):")
        for key, count in metadata_stats.items():
            print(f"  {key}: {count} unique values")
    
    # Show sample chunk
    print(f"\n=== Sample Chunk ===")
    sample = chunks[0]
    print(f"Text preview: {sample['text'][:200]}...")
    print(f"Chunk {sample['chunk_index'] + 1}/{sample['total_chunks']}")
    print(f"Metadata keys: {list(sample['metadata'].keys())}")

def chunk_file(
    file_path: str,
    output_path: str,
    chunk_size: int = 400,
    text_column: str = 'text',
    dropped_columns: List[str] = None,
    unit: str = 'words'
) -> List[Dict[str, Any]]:
    
    chunker = TextChunker(
        chunk_size=chunk_size,
        text_column=text_column,
        dropped_columns=dropped_columns or [],
        unit=unit
    )
    
    chunks = chunker.forward(file_path)
    
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        if output_file.suffix.lower() == '.json':
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(chunks, f, indent=2, ensure_ascii=False)
        elif output_file.suffix.lower() == '.csv':
            chunks_df = pd.json_normalize(chunks)
            chunks_df.to_csv(output_file, index=False)
        else:
            raise ValueError(f"Unsupported output format: {output_file.suffix}")
        
        print(f"\nSaved {len(chunks)} chunks to {output_file}")
    
    return chunks

def main():
    parser = argparse.ArgumentParser(description="Chunk text data for RAG processing")
    parser.add_argument("input", nargs='?', help="Input CSV or JSON file")
    parser.add_argument("-o", "--output", help="Output file for chunks")
    parser.add_argument("-s", "--chunk-size", type=int, default=400,
                       help="Chunk size in words or characters")
    parser.add_argument("-t", "--text-column", default='text',
                       help="Column containing text to chunk")
    parser.add_argument("-d", "--drop-columns", nargs='+', default=[],
                       help="Columns to drop (others become metadata)")
    parser.add_argument("-u", "--unit", choices=['words', 'characters'], default='words',
                       help="Unit for chunk size and overlap")
    parser.add_argument("--interactive", action="store_true",
                       help="Interactive mode: prompts for file paths and column selection")
    parser.add_argument("--stats", action="store_true",
                       help="Show detailed chunking statistics")
    
    args = parser.parse_args()
    
    # Interactive mode
    if args.interactive:
        input_file, output_file, text_column, dropped_columns = interactive_setup()
    else:
        # Non-interactive mode
        if not args.input:
            print("Error: Input file required (or use --interactive)")
            sys.exit(1)
        
        if not Path(args.input).exists():
            print(f"Error: Input file {args.input} not found")
            sys.exit(1)
        
        input_file = args.input
        output_file = args.output
        text_column = args.text_column
        dropped_columns = args.drop_columns
    
    print(f"\n=== Chunking Configuration ===")
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Text column: {text_column}")
    print(f"Dropped columns: {dropped_columns}")
    print(f"Chunk size: {args.chunk_size} {args.unit}")
    print("-" * 50)
    
    try:
        chunks = chunk_file(
            input_file,
            output_file,
            args.chunk_size,
            text_column,
            dropped_columns,
            args.unit
        )
        
        print_chunk_statistics(chunks, args.unit)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()