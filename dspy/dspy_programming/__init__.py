"""
DSPy Programming Phase - Naming Names Classification

This module contains the DSPy conversion of the original LLM classification system
for identifying aggressive state behavior in UN General Assembly speeches.

Main components:
- dspy_classifier.py: Core DSPy signature and module
- dspy_processor.py: Drop-in replacement for original processor
- config.py: DSPy model configuration  
- data_loader.py: NER dataset loading utilities
- test_conversion.py: Validation and testing scripts
- main.py: Main processing pipeline
"""

from .dspy_classifier import AggressorClassifier, AggressorClassification
from .dspy_processor import DSPyClassificationProcessor
from .config import setup_dspy_cohere
from .data_loader import load_ner_data, group_by_year, filter_by_years

__all__ = [
    'AggressorClassifier',
    'AggressorClassification', 
    'DSPyClassificationProcessor',
    'setup_dspy_cohere',
    'load_ner_data',
    'group_by_year',
    'filter_by_years'
]