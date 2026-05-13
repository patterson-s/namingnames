#!/usr/bin/env python3

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ExtractionStats:
    total_entries: int = 0
    successful_extractions: int = 0
    failed_entries: int = 0
    partial_extractions: int = 0
    total_relationships: int = 0
    
@dataclass
class ErrorRecord:
    line_num: int
    doc_id: str
    error_type: str
    error_message: str
    raw_content: str = ""

class GraphDataExtractor:
    def __init__(self, input_file: str, output_dir: str = "output"):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.stats = ExtractionStats()
        self.errors: List[ErrorRecord] = []
        
        self.setup_logging()
    
    def setup_logging(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.output_dir / f"extraction_log_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def clean_json_string(self, json_str: str) -> str:
        """Clean common JSON formatting issues from LLM output."""
        json_str = json_str.strip()
        
        # Remove markdown code blocks if present
        json_str = re.sub(r'^```(?:json|thinking|analysis)?\s*', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'^```\s*$', '', json_str, flags=re.MULTILINE)
        
        # Remove trailing commas before closing brackets/braces
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix common quote issues
        json_str = re.sub(r'"\s*:\s*"([^"]*)"([^",}\]]*)"', r'": "\1\2"', json_str)
        
        return json_str.strip()
    
    def extract_json_from_text(self, text: str) -> Optional[Dict]:
        """Extract JSON from mixed text content."""
        if not text:
            return None
            
        # Strategy 1: Try to find JSON between analysis tags with nested json code blocks
        analysis_match = re.search(r'<analysis>\s*```json\s*(\{.*?\})\s*```\s*</analysis>', text, re.DOTALL)
        if analysis_match:
            json_str = analysis_match.group(1)
            result = self.parse_json_safely(json_str)
            if result:
                return result
        
        # Strategy 2: Try to find JSON between analysis tags (simple format)
        analysis_match = re.search(r'<analysis>\s*(\{.*?\})\s*</analysis>', text, re.DOTALL)
        if analysis_match:
            json_str = analysis_match.group(1)
            result = self.parse_json_safely(json_str)
            if result:
                return result
        
        # Strategy 3: Try to find JSON between analysis code blocks (triple backticks)
        analysis_match = re.search(r'```analysis\s*(\{.*?\})\s*```', text, re.DOTALL)
        if analysis_match:
            json_str = analysis_match.group(1)
            result = self.parse_json_safely(json_str)
            if result:
                return result
        
        # Strategy 4: Look for JSON-like structure with source_country
        json_match = re.search(r'(\{[^{]*"source_country".*?\})', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            result = self.parse_json_safely(json_str)
            if result:
                return result
            
        # Strategy 5: Try to find any JSON object with bilateral_relationships
        json_match = re.search(r'(\{.*?"bilateral_relationships".*?\})', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            result = self.parse_json_safely(json_str)
            if result:
                return result
        
        return None
    
    def parse_json_safely(self, json_str: str) -> Optional[Dict]:
        """Attempt to parse JSON with multiple fallback strategies."""
        if not json_str:
            return None
            
        json_str = self.clean_json_string(json_str)
        
        # Strategy 1: Direct parsing
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Try to fix common bracket issues
        try:
            # Count braces and try to balance them
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            if open_braces > close_braces:
                json_str += '}' * (open_braces - close_braces)
            
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Strategy 3: Extract just the core structure
        try:
            # Look for the main structure pattern
            match = re.search(r'\{\s*"source_country".*?"bilateral_relationships".*?\].*?\}', json_str, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
        
        return None
    
    def validate_entry_structure(self, entry: Dict) -> Tuple[bool, str]:
        """Validate that an entry has the required basic structure."""
        # Check if this is the nested structure with 'result' field
        if 'result' in entry:
            result = entry['result']
            required_fields = ['doc_id', 'year', 'targets']
            
            for field in required_fields:
                if field not in result:
                    return False, f"Missing required field in result: {field}"
            
            if 'model_response' not in result:
                return False, "Missing model_response field in result"
        else:
            # Original flat structure
            required_fields = ['doc_id', 'source', 'year', 'targets']
            
            for field in required_fields:
                if field not in entry:
                    return False, f"Missing required field: {field}"
            
            if 'model_response' not in entry:
                return False, "Missing model_response field"
        
        return True, ""
    
    def validate_bilateral_relationship(self, relationship: Dict) -> Tuple[bool, str]:
        """Validate a single bilateral relationship structure."""
        required_fields = ['target_country', 'rhetorical_move', 'substantive_context']
        
        for field in required_fields:
            if field not in relationship:
                return False, f"Missing field in relationship: {field}"
        
        # Validate substantive_context structure
        if not isinstance(relationship['substantive_context'], dict):
            return False, "substantive_context must be a dictionary"
        
        context = relationship['substantive_context']
        if 'full_text' not in context or 'tags' not in context:
            return False, "substantive_context missing full_text or tags"
        
        if not isinstance(context['tags'], list):
            return False, "tags must be a list"
        
        return True, ""
    
    def extract_relationships_from_entry(self, entry: Dict) -> List[Dict]:
        """Extract and convert bilateral relationships to graph format."""
        relationships = []
        
        # Handle nested structure with 'result' field
        if 'result' in entry:
            result_data = entry['result']
            source = result_data.get('source')
            if not source:
                # Extract source from first 3 letters of doc_id
                doc_id = result_data.get('doc_id', '')
                source = doc_id[:3] if len(doc_id) >= 3 else ''
            
            year = result_data.get('year')
            targets = result_data.get('targets', [])
            model_response_str = result_data.get('model_response', '')
        else:
            # Original flat structure
            source = entry.get('source')
            if not source:
                # Extract source from first 3 letters of doc_id
                doc_id = entry.get('doc_id', '')
                source = doc_id[:3] if len(doc_id) >= 3 else ''
            
            year = entry.get('year')
            targets = entry.get('targets', [])
            model_response_str = entry.get('model_response', '')
        
        # Parse model_response
        if isinstance(model_response_str, str):
            model_response = self.extract_json_from_text(model_response_str)
        elif isinstance(model_response_str, dict):
            # model_response is already a parsed object
            model_response = model_response_str
        else:
            model_response = None
        
        if not model_response:
            doc_id = entry.get('doc_id') or (entry.get('result', {}).get('doc_id', 'unknown'))
            self.logger.warning(f"Could not parse model_response for {doc_id}")
            return relationships
        
        # Extract bilateral relationships
        bilateral_rels = model_response.get('bilateral_relationships', [])
        if not bilateral_rels:
            self.logger.warning(f"No bilateral relationships found for {entry.get('doc_id', 'unknown')}")
            return relationships
        
        # Convert each relationship to graph format
        for rel in bilateral_rels:
            is_valid, error_msg = self.validate_bilateral_relationship(rel)
            if not is_valid:
                self.logger.warning(f"Invalid relationship in {entry.get('doc_id', 'unknown')}: {error_msg}")
                continue
            
            # Extract the graph format
            graph_entry = {
                'source': source,
                'target': rel['target_country'],
                'year': year,
                'rhetorical_move': rel['rhetorical_move'],
                'full_text': rel['substantive_context']['full_text'],
                'tags': rel['substantive_context']['tags']
            }
            
            relationships.append(graph_entry)
        
        return relationships
    
    def process_file(self) -> List[Dict]:
        """Process the input JSONL file and extract graph format data."""
        self.logger.info(f"Starting extraction from {self.input_file}")
        
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        
        all_relationships = []
        line_num = 0
        
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line_num += 1
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    self.stats.total_entries += 1
                    
                    try:
                        # Parse the main JSONL entry
                        entry = json.loads(line)
                        
                        # Get doc_id from appropriate location
                        if 'result' in entry:
                            doc_id = entry['result'].get('doc_id', f'line_{line_num}')
                        else:
                            doc_id = entry.get('doc_id', f'line_{line_num}')
                        
                        # Validate entry structure
                        is_valid, error_msg = self.validate_entry_structure(entry)
                        if not is_valid:
                            self.record_error(line_num, doc_id, "STRUCTURE_ERROR", error_msg, line)
                            continue
                        
                        # Extract relationships
                        relationships = self.extract_relationships_from_entry(entry)
                        
                        if relationships:
                            all_relationships.extend(relationships)
                            self.stats.successful_extractions += 1
                            self.stats.total_relationships += len(relationships)
                            
                            # Debug: log the successful extraction
                            self.logger.info(f"Successfully extracted {len(relationships)} relationships from {doc_id}")
                            for i, rel in enumerate(relationships):
                                self.logger.info(f"  Relationship {i+1}: {rel['source']} -> {rel['target']} ({rel['year']})")
                            
                            # Check for partial extractions
                            expected_targets = entry.get('result', {}).get('targets', []) if 'result' in entry else entry.get('targets', [])
                            if len(relationships) < len(expected_targets):
                                self.stats.partial_extractions += 1
                                self.logger.info(f"Partial extraction for {doc_id}: {len(relationships)}/{len(expected_targets)} relationships")
                        else:
                            self.record_error(line_num, doc_id, "NO_RELATIONSHIPS", "No valid relationships extracted", "")
                    
                    except json.JSONDecodeError as e:
                        self.record_error(line_num, "unknown", "JSON_PARSE_ERROR", str(e), line)
                    except Exception as e:
                        self.record_error(line_num, "unknown", "PROCESSING_ERROR", str(e), line)
        
        except Exception as e:
            self.logger.error(f"Fatal error processing file: {e}")
            raise
        
        self.logger.info(f"Extraction complete. Processed {self.stats.total_entries} entries, extracted {self.stats.total_relationships} relationships")
        self.logger.info(f"Final relationship count before returning: {len(all_relationships)}")
        return all_relationships
    
    def record_error(self, line_num: int, doc_id: str, error_type: str, message: str, raw_content: str = ""):
        """Record an error for later reporting."""
        self.stats.failed_entries += 1
        error = ErrorRecord(line_num, doc_id, error_type, message, raw_content[:500])  # Truncate long content
        self.errors.append(error)
        self.logger.error(f"Line {line_num} ({doc_id}): {error_type} - {message}")
    
    def generate_reports(self, output_data: List[Dict]):
        """Generate summary report and error log."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save extracted data
        output_file = self.output_dir / f"graph_data_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        # Generate summary report
        success_rate = (self.stats.successful_extractions / self.stats.total_entries * 100) if self.stats.total_entries > 0 else 0
        
        report = f"""
EXTRACTION SUMMARY REPORT
=========================
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Input File: {self.input_file}
Output File: {output_file}

STATISTICS:
-----------
Total entries processed: {self.stats.total_entries}
Successful extractions: {self.stats.successful_extractions}
Failed entries: {self.stats.failed_entries}
Partial extractions: {self.stats.partial_extractions}
Total relationships extracted: {self.stats.total_relationships}
Success rate: {success_rate:.1f}%

ERROR BREAKDOWN:
----------------
"""
        
        # Count errors by type
        error_counts = {}
        for error in self.errors:
            error_counts[error.error_type] = error_counts.get(error.error_type, 0) + 1
        
        for error_type, count in error_counts.items():
            report += f"{error_type}: {count}\n"
        
        report += f"\nRECOMMENDations:\n"
        report += f"----------------\n"
        
        if self.stats.failed_entries > 0:
            report += f"- {self.stats.failed_entries} entries failed processing. See error log for details.\n"
        
        if self.stats.partial_extractions > 0:
            report += f"- {self.stats.partial_extractions} entries had partial extractions. Some targets may be missing analysis.\n"
        
        if success_rate < 90:
            report += f"- Success rate is {success_rate:.1f}%. Consider reviewing LLM output quality or adjusting parsing logic.\n"
        
        # Save summary report
        report_file = self.output_dir / f"extraction_report_{timestamp}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Save detailed error log
        if self.errors:
            error_file = self.output_dir / f"error_log_{timestamp}.json"
            error_data = [
                {
                    'line_num': err.line_num,
                    'doc_id': err.doc_id,
                    'error_type': err.error_type,
                    'error_message': err.error_message,
                    'raw_content': err.raw_content
                }
                for err in self.errors
            ]
            
            with open(error_file, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Reports generated:")
        self.logger.info(f"  - Data: {output_file}")
        self.logger.info(f"  - Summary: {report_file}")
        if self.errors:
            self.logger.info(f"  - Errors: {error_file}")
        
        print(report)
    
    def run(self) -> List[Dict]:
        """Run the complete extraction process."""
        try:
            extracted_data = self.process_file()
            self.generate_reports(extracted_data)
            return extracted_data
        except Exception as e:
            self.logger.error(f"Extraction failed: {e}")
            raise

def main():
    input_file = input("Enter the path to the input JSONL file: ").strip().strip('"')
    
    if not input_file:
        print("No input file provided. Exiting.")
        return
    
    try:
        extractor = GraphDataExtractor(input_file)
        results = extractor.run()
        
        print(f"\n✅ Extraction completed successfully!")
        print(f"📊 Extracted {len(results)} bilateral relationships")
        print(f"📁 Check the 'output' directory for results and reports")
        
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        raise

if __name__ == "__main__":
    main()