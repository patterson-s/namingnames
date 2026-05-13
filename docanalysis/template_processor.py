#!/usr/bin/env python3

import re
import json
from typing import Dict, Any, List


class TemplateProcessor:
    @staticmethod
    def substitute_variables(template: str, data: Dict[str, Any]) -> str:
        """Substitute {{variable}} placeholders with actual data"""
        if not template:
            return ""
        
        def replace_variable(match):
            var_name = match.group(1).strip()
            
            if var_name in data:
                value = data[var_name]
                
                # Handle different data types
                if value is None:
                    return ""
                elif isinstance(value, (dict, list)):
                    # For complex types, convert to JSON string
                    return json.dumps(value, indent=2)
                else:
                    return str(value)
            else:
                # Keep placeholder if variable not found
                return f"{{{{ {var_name} }}}}"
        
        # Replace {{variable}} patterns
        result = re.sub(r'\{\{\s*([^}]+)\s*\}\}', replace_variable, template)
        return result
    
    @staticmethod
    def find_variables(template: str) -> List[str]:
        """Find all {{variable}} placeholders in template"""
        if not template:
            return []
        
        matches = re.findall(r'\{\{\s*([^}]+)\s*\}\}', template)
        return [match.strip() for match in matches]
    
    @staticmethod
    def validate_template(template: str, available_variables: List[str]) -> List[str]:
        """Validate template and return list of missing variables"""
        if not template:
            return []
        
        used_variables = TemplateProcessor.find_variables(template)
        missing = [var for var in used_variables if var not in available_variables]
        return missing
    
    @staticmethod
    def prepare_document_variables(document: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare all possible variables from a document for template substitution"""
        variables = {}
        
        # Add all keys from the document
        for key, value in document.items():
            variables[key] = value
        
        # Ensure we have all the standard variables
        variables.setdefault('doc_id', document.get('doc_id', ''))
        variables.setdefault('source', document.get('source', ''))
        variables.setdefault('year', document.get('year', ''))
        variables.setdefault('targets', document.get('targets', []))
        variables.setdefault('targets_list', document.get('targets_list', ''))
        variables.setdefault('total_statements', document.get('total_statements', 0))
        
        # Add the various formatted representations
        variables.setdefault('statements_formatted', document.get('statements_formatted', ''))
        variables.setdefault('statements_by_target_formatted', document.get('statements_by_target_formatted', ''))
        variables.setdefault('statements_json', document.get('statements_json', '{}'))
        variables.setdefault('statements_by_target_json', document.get('statements_by_target_json', '{}'))
        
        return variables
    
    @staticmethod
    def get_available_variables(document: Dict[str, Any]) -> List[str]:
        """Get list of all available variables for a document"""
        variables = TemplateProcessor.prepare_document_variables(document)
        return sorted(list(variables.keys()))