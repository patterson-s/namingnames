import streamlit as st
import json
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime
import io

def load_jsonl_data(uploaded_file) -> List[Dict[str, Any]]:
    """Load data from uploaded JSONL file"""
    try:
        content = uploaded_file.read().decode('utf-8')
        lines = content.strip().split('\n')
        data = []
        for line in lines:
            if line.strip():
                data.append(json.loads(line))
        return data
    except Exception as e:
        st.error(f"Error loading file: {str(e)}")
        return []

def validate_data_format(data: List[Dict[str, Any]]) -> bool:
    """Validate that data has required fields"""
    if not data:
        return False
    
    required_fields = ['text', 'target', 'classification']
    sample = data[0]
    
    missing_fields = [field for field in required_fields if field not in sample]
    if missing_fields:
        st.error(f"Missing required fields: {missing_fields}")
        return False
    
    return True

def create_download_link(corrected_examples: List[Dict[str, Any]]) -> str:
    """Create downloadable JSONL content"""
    if not corrected_examples:
        return ""
    
    jsonl_content = ""
    for example in corrected_examples:
        jsonl_content += json.dumps(example) + "\n"
    
    return jsonl_content

def display_example(example: Dict[str, Any]) -> None:
    """Display the current example details"""
    st.subheader("Example Details")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(f"**Source Country:** {example.get('source_country', 'N/A')}")
    with col2:
        st.write(f"**Target Country:** {example.get('target', 'N/A')}")
    with col3:
        st.write(f"**Year:** {example.get('year', 'N/A')}")
    
    st.write("**Full Text:**")
    st.text_area("", value=example.get('text', ''), height=150, key="display_text", label_visibility="collapsed")
    
    st.write("**Model Output:**")
    model_output = f"""Classification: {example.get('classification', '')}
Victims: {example.get('victims', '')}
Reasoning: {example.get('reasoning', '')}

Full Response:
{example.get('full_response', '')}"""
    
    st.text_area("", value=model_output, height=200, key="display_output", label_visibility="collapsed")

def edit_template(example: Dict[str, Any]) -> Dict[str, str]:
    """Create editable template for corrections"""
    st.subheader("Gold Standard Template")
    st.write("Edit the fields below to create the correct output:")
    
    corrected_classification = st.selectbox(
        "Classification",
        options=['0', '1'],
        index=0 if example.get('classification', '0') == '0' else 1,
        key="edit_classification"
    )
    
    corrected_victims = st.text_input(
        "Victims (semicolon separated)",
        value=example.get('victims', ''),
        key="edit_victims"
    )
    
    corrected_reasoning = st.text_area(
        "Reasoning (provide clear explanation)",
        value=example.get('reasoning', ''),
        height=100,
        key="edit_reasoning"
    )
    
    return {
        'classification': corrected_classification,
        'victims': corrected_victims,
        'reasoning': corrected_reasoning
    }

def main():
    st.title("DSPy Evaluation Interface")
    st.write("Upload your data file and create gold standard examples for DSPy optimization.")
    
    # Initialize session state
    if 'data' not in st.session_state:
        st.session_state.data = []
    if 'current_index' not in st.session_state:
        st.session_state.current_index = 0
    if 'corrected_examples' not in st.session_state:
        st.session_state.corrected_examples = []
    if 'skipped_indices' not in st.session_state:
        st.session_state.skipped_indices = set()
    
    # File upload section
    st.header("1. Upload Data File")
    uploaded_file = st.file_uploader(
        "Choose a JSONL file",
        type=['jsonl'],
        help="Upload your JSONL file containing examples to evaluate"
    )
    
    if uploaded_file is not None:
        # Load and validate data
        if not st.session_state.data:
            st.session_state.data = load_jsonl_data(uploaded_file)
            
        if st.session_state.data and validate_data_format(st.session_state.data):
            # Data summary
            st.success(f"Loaded {len(st.session_state.data)} examples successfully!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Examples", len(st.session_state.data))
            with col2:
                st.metric("Corrected", len(st.session_state.corrected_examples))
            with col3:
                st.metric("Skipped", len(st.session_state.skipped_indices))
            
            # Progress bar
            progress = (st.session_state.current_index) / len(st.session_state.data)
            st.progress(progress)
            st.write(f"Progress: {st.session_state.current_index}/{len(st.session_state.data)} examples reviewed")
            
            # Navigation
            st.header("2. Review Examples")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("← Previous", disabled=st.session_state.current_index == 0):
                    st.session_state.current_index = max(0, st.session_state.current_index - 1)
                    st.rerun()
            
            with col2:
                st.write(f"Example {st.session_state.current_index + 1}")
            
            with col3:
                if st.button("Next →", disabled=st.session_state.current_index >= len(st.session_state.data) - 1):
                    st.session_state.current_index = min(len(st.session_state.data) - 1, st.session_state.current_index + 1)
                    st.rerun()
            
            # Display current example
            if st.session_state.current_index < len(st.session_state.data):
                current_example = st.session_state.data[st.session_state.current_index]
                
                display_example(current_example)
                
                # Check if already processed
                is_corrected = any(ex.get('original_index') == st.session_state.current_index 
                                 for ex in st.session_state.corrected_examples)
                is_skipped = st.session_state.current_index in st.session_state.skipped_indices
                
                if is_corrected:
                    st.success("✅ This example has been corrected and saved.")
                elif is_skipped:
                    st.info("⏭️ This example has been skipped.")
                
                # Edit template
                corrections = edit_template(current_example)
                
                # Action buttons
                st.header("3. Actions")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("Skip Example", type="secondary"):
                        st.session_state.skipped_indices.add(st.session_state.current_index)
                        if st.session_state.current_index < len(st.session_state.data) - 1:
                            st.session_state.current_index += 1
                        st.rerun()
                
                with col2:
                    if st.button("Save as Gold Standard", type="primary"):
                        # Create corrected example
                        corrected_example = {
                            **current_example,  # Keep original data
                            'correct_classification': corrections['classification'],
                            'correct_victims': corrections['victims'],
                            'correct_reasoning': corrections['reasoning'],
                            'corrected_at': datetime.now().isoformat(),
                            'original_index': st.session_state.current_index
                        }
                        
                        # Remove if already exists and add new version
                        st.session_state.corrected_examples = [
                            ex for ex in st.session_state.corrected_examples 
                            if ex.get('original_index') != st.session_state.current_index
                        ]
                        st.session_state.corrected_examples.append(corrected_example)
                        
                        # Remove from skipped if it was there
                        st.session_state.skipped_indices.discard(st.session_state.current_index)
                        
                        # Move to next example
                        if st.session_state.current_index < len(st.session_state.data) - 1:
                            st.session_state.current_index += 1
                        
                        st.success("Example saved as gold standard!")
                        st.rerun()
                
                with col3:
                    # Download button
                    if st.session_state.corrected_examples:
                        jsonl_content = create_download_link(st.session_state.corrected_examples)
                        st.download_button(
                            label=f"Download {len(st.session_state.corrected_examples)} Corrected Examples",
                            data=jsonl_content,
                            file_name=f"gold_standard_examples_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
                            mime="application/json"
                        )
            
            # Summary section
            if st.session_state.corrected_examples:
                st.header("4. Summary")
                
                # Show corrected examples summary
                df_summary = []
                for ex in st.session_state.corrected_examples:
                    df_summary.append({
                        'Source': ex.get('source_country', ''),
                        'Target': ex.get('target', ''),
                        'Year': ex.get('year', ''),
                        'Classification': ex.get('correct_classification', ''),
                        'Original Index': ex.get('original_index', '')
                    })
                
                if df_summary:
                    st.write("**Corrected Examples:**")
                    st.dataframe(pd.DataFrame(df_summary))

if __name__ == "__main__":
    main()