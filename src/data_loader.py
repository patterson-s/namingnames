import os
import json
import csv
from typing import List, Dict, Optional, Union
from pathlib import Path


class SpeechData:
    def __init__(self, content: str, country: str, year: str, identifier: str):
        self.content = content
        self.country = country
        self.year = year
        self.identifier = identifier


class DataLoader:
    def __init__(self, input_path: str):
        self.input_path = Path(input_path)
        
    def load_speeches(self, batch_size: int = 5, max_speeches: Optional[int] = None) -> List[List[SpeechData]]:
        """Load speeches and return them in batches"""
        if self.input_path.is_file() and self.input_path.suffix.lower() == '.csv':
            speeches = self._load_from_csv()
        else:
            speeches = self._load_from_directory()
        
        if max_speeches:
            speeches = speeches[:max_speeches]
        
        # Split into batches
        batches = []
        for i in range(0, len(speeches), batch_size):
            batches.append(speeches[i:i + batch_size])
        
        return batches
    
    def _load_from_csv(self) -> List[SpeechData]:
        speeches = []
        
        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Handle the CSV structure from your data
                    iso = row.get('iso', 'Unknown')
                    year = str(row.get('year', 'Unknown'))
                    text = row.get('text', '').strip()
                    
                    if text and iso and year:
                        speech_data = SpeechData(
                            content=text,
                            country=iso,
                            year=year,
                            identifier=f"{iso}_{year}"
                        )
                        speeches.append(speech_data)
                        
        except Exception as e:
            print(f"Error loading CSV {self.input_path}: {e}")
            return []
        
        speeches.sort(key=lambda x: (x.year, x.country))
        return speeches
    
    def _load_from_directory(self) -> List[SpeechData]:
        """Legacy method for loading from directory of files"""
        speeches = []
        
        if not self.input_path.is_dir():
            return speeches
        
        for file_path in self.input_path.glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.txt', '.md', '.json']:
                speech_data = self._load_single_speech(file_path)
                if speech_data:
                    speeches.append(speech_data)
        
        speeches.sort(key=lambda x: (x.year, x.country))
        return speeches
    
    def _load_single_speech(self, file_path: Path) -> Optional[SpeechData]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if file_path.suffix.lower() == '.json':
                data = json.loads(content)
                return SpeechData(
                    content=data.get('content', data.get('text', '')),
                    country=data.get('country', 'Unknown'),
                    year=str(data.get('year', 'Unknown')),
                    identifier=file_path.name
                )
            else:
                country, year = self._parse_filename(file_path.name)
                return SpeechData(
                    content=content,
                    country=country,
                    year=year,
                    identifier=file_path.name
                )
                
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None
    
    def _parse_filename(self, filename: str) -> tuple[str, str]:
        parts = filename.replace('.txt', '').replace('.md', '').split('_')
        
        if len(parts) >= 2:
            if parts[1].isdigit():
                return parts[0], parts[1]
            elif parts[0].isdigit():
                return parts[1], parts[0]
        
        return parts[0] if parts else 'Unknown', 'Unknown'