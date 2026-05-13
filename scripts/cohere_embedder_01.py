#!/usr/bin/env python3

import dspy
import cohere
import numpy as np
import json
import argparse
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import time
from collections import defaultdict

class TextEmbedder(dspy.Module):
    def __init__(self, model_name: str = "embed-v4.0", batch_size: int = 96):
        super().__init__()
        load_dotenv()
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY not found in environment")
        
        self.client = cohere.ClientV2(api_key)
        self.model_name = model_name
        self.batch_size = batch_size
        
    def _embed_texts(self, texts: List[str], input_type: str = "search_document", 
                    output_dir: Path = None, resume_from: int = 0) -> np.ndarray:
        all_embeddings = []
        checkpoint_file = output_dir / "embedding_checkpoint.npy" if output_dir else None
        progress_file = output_dir / "embedding_progress.json" if output_dir else None
        
        if resume_from > 0 and checkpoint_file and checkpoint_file.exists():
            print(f"Resuming from batch {resume_from}")
            all_embeddings = np.load(checkpoint_file).tolist()
        
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        
        for i in range(resume_from * self.batch_size, len(texts), self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = texts[i:i + self.batch_size]
            print(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} texts)")
            
            retry_count = 0
            max_retries = 3
            
            while retry_count <= max_retries:
                try:
                    response = self.client.embed(
                        model=self.model_name,
                        input_type=input_type,
                        texts=batch,
                        embedding_types=["float"],
                    )
                    
                    batch_embeddings = response.embeddings.float
                    all_embeddings.extend(batch_embeddings)
                    
                    if checkpoint_file and batch_num % 50 == 0:
                        np.save(checkpoint_file, np.array(all_embeddings))
                        if progress_file:
                            with open(progress_file, 'w') as f:
                                json.dump({
                                    'last_batch': batch_num,
                                    'total_batches': total_batches,
                                    'completed_texts': len(all_embeddings)
                                }, f)
                        print(f"  → Checkpoint saved at batch {batch_num}")
                    
                    time.sleep(0.2)
                    break
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count
                        print(f"  → Error in batch {batch_num} (attempt {retry_count}/{max_retries + 1}): {e}")
                        print(f"  → Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        print(f"  → Failed batch {batch_num} after {max_retries + 1} attempts: {e}")
                        if checkpoint_file and all_embeddings:
                            np.save(checkpoint_file, np.array(all_embeddings))
                            if progress_file:
                                with open(progress_file, 'w') as f:
                                    json.dump({
                                        'last_batch': batch_num - 1,
                                        'total_batches': total_batches,
                                        'completed_texts': len(all_embeddings),
                                        'failed_at_batch': batch_num,
                                        'error': str(e)
                                    }, f)
                        raise RuntimeError(f"Failed to embed batch {batch_num} after {max_retries + 1} attempts: {e}")
        
        if checkpoint_file and checkpoint_file.exists():
            checkpoint_file.unlink()
        if progress_file and progress_file.exists():
            progress_file.unlink()
        
        return np.array(all_embeddings)
    
    def build_metadata_index(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        indexes = defaultdict(lambda: defaultdict(list))
        
        for i, chunk in enumerate(chunks):
            metadata = chunk.get('metadata', {})
            
            for key, value in metadata.items():
                if value is not None:
                    value_str = str(value).strip()
                    if value_str:
                        indexes[key][value_str].append(i)
        
        return dict(indexes)
    
    def forward(
        self, 
        chunks_file: str, 
        output_dir: str = None, 
        force_recompute: bool = False,
        resume: bool = True
    ) -> Dict[str, Any]:
        
        chunks_path = Path(chunks_file)
        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_file}")
        
        if output_dir is None:
            output_dir = chunks_path.parent / "embeddings"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        embeddings_file = output_dir / "embeddings.npy"
        metadata_file = output_dir / "chunks_metadata.json"
        index_file = output_dir / "metadata_index.json"
        progress_file = output_dir / "embedding_progress.json"
        
        if not force_recompute and all(f.exists() for f in [embeddings_file, metadata_file, index_file]):
            print("Loading existing embeddings...")
            embeddings = np.load(embeddings_file)
            with open(metadata_file, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            with open(index_file, 'r', encoding='utf-8') as f:
                metadata_index = json.load(f)
            
            return {
                'embeddings': embeddings,
                'chunks': chunks,
                'metadata_index': metadata_index,
                'embedding_dim': embeddings.shape[1],
                'num_chunks': len(chunks)
            }
        
        print(f"Loading chunks from {chunks_file}")
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"Found {len(chunks)} chunks")
        
        resume_from_batch = 0
        if resume and progress_file.exists():
            with open(progress_file, 'r') as f:
                progress = json.load(f)
            resume_from_batch = progress.get('last_batch', 0)
            print(f"Found progress file - can resume from batch {resume_from_batch}")
            
            user_input = input(f"Resume from batch {resume_from_batch}? (y/n): ").strip().lower()
            if user_input == 'y':
                print(f"Resuming from batch {resume_from_batch}")
            else:
                resume_from_batch = 0
                print("Starting from beginning")
        
        texts = [chunk['text'] for chunk in chunks]
        print(f"Extracting text from {len(texts)} chunks...")
        
        print(f"Embedding texts using {self.model_name}...")
        print(f"Output directory: {output_dir}")
        
        embeddings = self._embed_texts(
            texts, 
            input_type="search_document",
            output_dir=output_dir,
            resume_from=resume_from_batch
        )
        
        print(f"Generated embeddings shape: {embeddings.shape}")
        
        print("Building metadata index...")
        metadata_index = self.build_metadata_index(chunks)
        
        print(f"Saving final embeddings to {output_dir}")
        np.save(embeddings_file, embeddings)
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(metadata_index, f, indent=2, ensure_ascii=False)
        
        print("Embedding complete!")
        print(f"  Embeddings: {embeddings_file}")
        print(f"  Metadata: {metadata_file}")
        print(f"  Index: {index_file}")
        
        return {
            'embeddings': embeddings,
            'chunks': chunks,
            'metadata_index': metadata_index,
            'embedding_dim': embeddings.shape[1],
            'num_chunks': len(chunks)
        }
    
    def embed_query(self, query: str) -> np.ndarray:
        response = self.client.embed(
            model=self.model_name,
            input_type="search_query",
            texts=[query],
            embedding_types=["float"],
        )
        return np.array(response.embeddings.float[0])

class EmbeddingLoader:
    def __init__(self, embeddings_dir: str):
        self.embeddings_dir = Path(embeddings_dir)
        self._embeddings = None
        self._chunks = None
        self._metadata_index = None
        
    def load(self) -> Dict[str, Any]:
        if self._embeddings is None:
            embeddings_file = self.embeddings_dir / "embeddings.npy"
            metadata_file = self.embeddings_dir / "chunks_metadata.json"
            index_file = self.embeddings_dir / "metadata_index.json"
            
            if not all(f.exists() for f in [embeddings_file, metadata_file, index_file]):
                raise FileNotFoundError(f"Missing embedding files in {self.embeddings_dir}")
            
            self._embeddings = np.load(embeddings_file)
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                self._chunks = json.load(f)
                
            with open(index_file, 'r', encoding='utf-8') as f:
                self._metadata_index = json.load(f)
        
        return {
            'embeddings': self._embeddings,
            'chunks': self._chunks,
            'metadata_index': self._metadata_index,
            'embedding_dim': self._embeddings.shape[1],
            'num_chunks': len(self._chunks)
        }
    
    def get_chunks_by_metadata(self, **filters) -> List[int]:
        data = self.load()
        metadata_index = data['metadata_index']
        
        if not filters:
            return list(range(len(data['chunks'])))
        
        result_indices = None
        
        for key, value in filters.items():
            if key not in metadata_index:
                return []
            
            value_str = str(value)
            if value_str not in metadata_index[key]:
                return []
            
            current_indices = set(metadata_index[key][value_str])
            
            if result_indices is None:
                result_indices = current_indices
            else:
                result_indices = result_indices.intersection(current_indices)
                
            if not result_indices:
                break
        
        return sorted(list(result_indices or []))

def interactive_setup() -> tuple[str, str]:
    print("=== Interactive Text Embedder Setup ===\n")
    
    while True:
        chunks_file = input("Enter the path to your chunks JSON file: ").strip()
        if not chunks_file:
            print("Please provide a file path.")
            continue
        
        chunks_path = Path(chunks_file)
        if not chunks_path.exists():
            print(f"File not found: {chunks_file}")
            continue
        
        if chunks_path.suffix.lower() != '.json':
            print("File must be JSON format.")
            continue
        
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            
            if not isinstance(chunks, list) or not chunks:
                print("File must contain a non-empty list of chunks.")
                continue
            
            sample_chunk = chunks[0]
            if 'text' not in sample_chunk:
                print("Chunks must have 'text' field.")
                continue
            
            print(f"✓ Loaded {len(chunks)} chunks")
            break
            
        except Exception as e:
            print(f"Error reading file: {e}")
            continue
    
    output_dir = input("\nEnter output directory for embeddings (or press Enter for default): ").strip()
    if not output_dir:
        output_dir = str(chunks_path.parent / "embeddings")
        print(f"Using default output directory: {output_dir}")
    
    return chunks_file, output_dir

def print_embedding_statistics(result: Dict[str, Any]) -> None:
    print(f"\n=== Embedding Statistics ===")
    print(f"Total chunks embedded: {result['num_chunks']:,}")
    print(f"Embedding dimension: {result['embedding_dim']}")
    print(f"Memory usage: ~{result['embeddings'].nbytes / 1024 / 1024:.1f} MB")
    print()
    
    print("Available metadata fields:")
    metadata_index = result['metadata_index']
    for field, values in metadata_index.items():
        print(f"  {field}: {len(values)} unique values")
        top_values = sorted(values.items(), key=lambda x: len(x[1]), reverse=True)[:3]
        for value, indices in top_values:
            print(f"    '{value}': {len(indices)} chunks")
    print()
    
    sample_chunk = result['chunks'][0]
    print("=== Sample Chunk ===")
    print(f"Text preview: {sample_chunk['text'][:150]}...")
    print(f"Metadata: {sample_chunk['metadata']}")
    print(f"Embedding shape: {result['embeddings'][0].shape}")

def embed_chunks(
    chunks_file: str,
    output_dir: str = None,
    batch_size: int = 96,
    force_recompute: bool = False,
    resume: bool = True
) -> Dict[str, Any]:
    
    embedder = TextEmbedder(batch_size=batch_size)
    return embedder.forward(chunks_file, output_dir, force_recompute, resume)

def show_metadata_stats(embeddings_dir: str):
    loader = EmbeddingLoader(embeddings_dir)
    data = loader.load()
    print_embedding_statistics(data)

def main():
    parser = argparse.ArgumentParser(description="Embed text chunks using Cohere")
    parser.add_argument("chunks_file", nargs='?', help="Path to chunks JSON file")
    parser.add_argument("-o", "--output", help="Output directory for embeddings")
    parser.add_argument("-b", "--batch-size", type=int, default=96,
                       help="Batch size for embedding API calls")
    parser.add_argument("-f", "--force", action="store_true",
                       help="Force recompute embeddings even if they exist")
    parser.add_argument("--no-resume", action="store_true",
                       help="Don't resume from checkpoint, start fresh")
    parser.add_argument("--interactive", action="store_true",
                       help="Interactive mode: prompts for file paths")
    parser.add_argument("--stats", action="store_true",
                       help="Show metadata statistics")
    parser.add_argument("--test-filter", nargs=2, metavar=("KEY", "VALUE"),
                       help="Test metadata filtering")
    
    args = parser.parse_args()
    
    if args.interactive:
        chunks_file, output_dir = interactive_setup()
    else:
        if not args.chunks_file:
            print("Error: Chunks file required (or use --interactive)")
            sys.exit(1)
        
        if not Path(args.chunks_file).exists():
            print(f"Error: Chunks file {args.chunks_file} not found")
            sys.exit(1)
        
        chunks_file = args.chunks_file
        output_dir = args.output
    
    try:
        if args.stats and output_dir and Path(output_dir).exists():
            show_metadata_stats(output_dir)
        elif args.test_filter and output_dir and Path(output_dir).exists():
            loader = EmbeddingLoader(output_dir)
            key, value = args.test_filter
            indices = loader.get_chunks_by_metadata(**{key: value})
            print(f"Found {len(indices)} chunks with {key}='{value}'")
            if indices:
                data = loader.load()
                sample_chunk = data['chunks'][indices[0]]
                print(f"Sample chunk metadata: {sample_chunk['metadata']}")
        else:
            print(f"\n=== Embedding Configuration ===")
            print(f"Chunks file: {chunks_file}")
            print(f"Output directory: {output_dir}")
            print(f"Batch size: {args.batch_size}")
            if args.force:
                print("Force recompute: True")
            print("-" * 50)
            
            result = embed_chunks(
                chunks_file,
                output_dir,
                args.batch_size,
                args.force,
                not args.no_resume
            )
            
            print_embedding_statistics(result)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()