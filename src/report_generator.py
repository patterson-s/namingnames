import os
from pathlib import Path
from datetime import datetime
from response_parser import ResponseParser


class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_reports(self, typology_response: str, full_conversation: str, speeches_analyzed: int):
        self._generate_typology_report(typology_response, speeches_analyzed)
        self._generate_full_conversation_report(full_conversation)
        print(f"Reports generated in {self.output_dir}")
    
    def _generate_typology_report(self, typology_response: str, speeches_count: int):
        reasoning, analysis = ResponseParser.parse_xml_response(typology_response)
        
        if not analysis:
            analysis = typology_response
        
        report_content = f"""# Diplomatic Speech Analysis: Characterization Typologies

**Analysis Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Speeches Analyzed:** {speeches_count}

## Methodology

This analysis employed an inductive approach to identify patterns in how countries characterize themselves and other nations in diplomatic speeches. Each speech was analyzed sequentially, building cumulative understanding of characterization strategies.

## Analytical Process

{reasoning if reasoning else "See full conversation for detailed reasoning process."}

## Results

{analysis}

## Notes

This typology was generated through systematic analysis of diplomatic speeches using large language models. The categories represent observed patterns in the data and serve as a framework for understanding diplomatic rhetoric strategies.

For the complete analysis process, see the full conversation report.
"""
        
        output_file = self.output_dir / "typology_report.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
    
    def _generate_full_conversation_report(self, conversation: str):
        report_content = f"""# Complete Analysis Conversation

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This document contains the complete conversation history of the diplomatic speech analysis, showing the step-by-step development of patterns and insights.

---

{conversation}

---

*End of conversation*
"""
        
        output_file = self.output_dir / "full_conversation.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_content)