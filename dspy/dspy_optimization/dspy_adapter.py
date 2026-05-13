import sys
from pathlib import Path
import dspy
import logging

# Add the programming directory to path for imports
sys.path.append(str(Path("../dspy_programming").resolve()))

try:
    from raw_processor import RawDSPyProcessor
    from config import setup_dspy_cohere
except ImportError as e:
    logging.error(f"Could not import from dspy_programming: {e}")
    logging.error("Make sure you're running from the dspy_optimization directory")
    raise

class DSPyAggressorClassifier(dspy.Module):
    """DSPy module wrapper around RawDSPyProcessor"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize the raw processor
        self.processor = RawDSPyProcessor()
        
        # Define the signature for DSPy
        # This tells DSPy what inputs and outputs to expect
        self.classify = dspy.Predict(
            "text: str, target: str -> classification: str, victims: str, reasoning: str"
        )
    
    def forward(self, text: str, target: str):
        """Process text and target to get classification"""
        try:
            # Create item in format expected by RawDSPyProcessor
            item = {
                'text': text,
                'target': target,
                'year': 2000,  # Dummy year
                'source_country': 'UNK',  # Dummy source
                'chunk_id': 'test'  # Dummy chunk
            }
            
            # Process using the raw processor
            result = self.processor.process_single(item)
            
            if result:
                # Return in DSPy Prediction format
                return dspy.Prediction(
                    classification=result.get('classification', '0'),
                    victims=result.get('victims', ''),
                    reasoning=result.get('reasoning', ''),
                    full_response=result.get('full_response', '')
                )
            else:
                # Fallback if processing failed
                logging.warning("RawDSPyProcessor returned None, using fallback")
                return dspy.Prediction(
                    classification='0',
                    victims='',
                    reasoning='Processing failed',
                    full_response='Error: Could not process input'
                )
                
        except Exception as e:
            logging.error(f"Error in DSPyAggressorClassifier: {e}")
            return dspy.Prediction(
                classification='0',
                victims='',
                reasoning=f'Error: {str(e)}',
                full_response=f'Error occurred: {str(e)}'
            )

def test_classifier():
    """Test the DSPy classifier"""
    
    # Setup DSPy
    setup_dspy_cohere()
    
    # Create classifier
    classifier = DSPyAggressorClassifier()
    
    # Test with sample input
    sample_text = """The United States has been supplying arms to various conflicts around the world, 
    contributing to ongoing violence and instability in these regions."""
    
    sample_target = "USA"
    
    print("Testing DSPy Aggressor Classifier")
    print("=" * 40)
    print(f"Text: {sample_text}")
    print(f"Target: {sample_target}")
    print()
    
    try:
        # Run the classifier
        result = classifier(text=sample_text, target=sample_target)
        
        print("Results:")
        print("-" * 20)
        print(f"Classification: {result.classification}")
        print(f"Victims: {result.victims}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Full Response Length: {len(result.full_response)} characters")
        
        return True
        
    except Exception as e:
        print(f"Error testing classifier: {e}")
        return False

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Test the classifier
    success = test_classifier()
    
    if success:
        print("\n✅ DSPy adapter working correctly!")
    else:
        print("\n❌ DSPy adapter test failed")