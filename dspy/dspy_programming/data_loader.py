import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict

def load_ner_data(file_path: Path | str) -> List[Dict[str, Any]]:
    """Load and process the NER dataset to create text-target pairs"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    processed_items = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for item in data:
        if not is_valid_ner_item(item):
            continue
            
        # Extract text and metadata
        text = item["text"]
        year = item["metadata"]["year"]
        iso = item["metadata"]["iso"]
        
        # Get all country entities found in this chunk
        country_entities = item.get("cleaned_codes", [])
        
        # Deduplicate target countries and exclude self-mentions
        unique_targets = set(country_entities)
        unique_targets.discard(iso)  # Remove self-mentions
        
        # Create a text-target pair for each unique country mentioned
        for target_country in unique_targets:
            processed_items.append({
                "text": text,
                "target": target_country,
                "year": year,
                "source_country": iso,
                "chunk_id": f"{iso}_{item['chunk_index']}_{year}",
                "doc_id": item["metadata"]["doc_id"]
            })
    
    logging.info(f"Loaded {len(processed_items)} text-target pairs from {len(data)} chunks")
    return processed_items

def group_by_year(items: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Group processed items by year"""
    grouped = defaultdict(list)
    for item in items:
        grouped[item["year"]].append(item)
    return dict(grouped)

def filter_by_years(items: List[Dict[str, Any]], years: Set[int]) -> List[Dict[str, Any]]:
    """Filter items to only include specified years"""
    return [item for item in items if item["year"] in years]

def is_valid_ner_item(item: Dict[str, Any]) -> bool:
    """Validate that NER item has required fields"""
    required_fields = ["text", "metadata", "cleaned_codes"]
    
    if not all(field in item for field in required_fields):
        return False
        
    if not item["text"] or not item["text"].strip():
        return False
        
    metadata = item["metadata"]
    required_metadata = ["year", "iso", "doc_id"]
    
    if not all(field in metadata for field in required_metadata):
        return False
        
    return True