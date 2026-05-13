import re
from typing import Tuple, Optional


class ResponseParser:
    @staticmethod
    def parse_xml_response(response: str) -> Tuple[Optional[str], Optional[str]]:
        reasoning_match = re.search(r'<REASONING>(.*?)</REASONING>', response, re.DOTALL)
        analysis_match = re.search(r'<ANALYSIS>(.*?)</ANALYSIS>', response, re.DOTALL)
        
        reasoning = reasoning_match.group(1).strip() if reasoning_match else None
        analysis = analysis_match.group(1).strip() if analysis_match else None
        
        return reasoning, analysis
    
    @staticmethod
    def validate_response(response: str) -> bool:
        has_reasoning = '<REASONING>' in response and '</REASONING>' in response
        has_analysis = '<ANALYSIS>' in response and '</ANALYSIS>' in response
        return has_reasoning and has_analysis
    
    @staticmethod
    def clean_response(response: str) -> str:
        response = response.strip()
        response = re.sub(r'\n\s*\n\s*\n', '\n\n', response)
        return response