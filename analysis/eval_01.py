import streamlit as st
import json
import pandas as pd
import random
import os
from datetime import datetime
from collections import Counter

# Load the unified data
@st.cache_data
def load_unified_data():
    with open(r"C:\Users\spatt\Desktop\namingnames\analysis\unified_01.json", 'r') as f:
        data = json.load(f)
    metadata = data.pop('_metadata', {})
    return data, metadata

def load_existing_evaluations():
    """Load existing evaluations to avoid duplicates"""
    eval_path = r"C:\Users\spatt\Desktop\namingnames\analysis\eval_01\eval_01.json"
    if os.path.exists(eval_path):
        with open(eval_path, 'r') as f:
            return json.load(f)
    return {}

def save_evaluation(relationship_key, evaluated_data, mode):
    """Save evaluation to eval_01.json"""
    eval_path = r"C:\Users\spatt\Desktop\namingnames\analysis\eval_01\eval_01.json"
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(eval_path), exist_ok=True)
    
    # Load existing evaluations
    existing_evals = load_existing_evaluations()
    
    # Add metadata about evaluation
    evaluated_data['_evaluation_metadata'] = {
        'mode': mode,
        'timestamp': datetime.now().isoformat(),
        'relationship_key': relationship_key
    }
    
    # Add this evaluation
    existing_evals[relationship_key] = evaluated_data
    
    # Save back to file
    with open(eval_path, 'w') as f:
        json.dump(existing_evals, f, indent=2)

def get_available_relationships(unified_data, existing_evaluations):
    """Get relationships that haven't been evaluated yet"""
    all_relationships = set(unified_data.keys())
    evaluated_relationships = set(existing_evaluations.keys())
    return list(all_relationships - evaluated_relationships)

def get_default_bilateral_classification(statements):
    """Calculate default bilateral classification from statement classifications"""
    # Get all non-null classifications
    classifications = [s['classification'] for s in statements 
                      if s['classification'] is not None]
    
    if not classifications:
        return "no_data"
    
    # Count occurrences
    counts = Counter(classifications)
    max_count = max(counts.values())
    most_common = [k for k, v in counts.items() if v == max_count]
    
    if len(most_common) == 1:
        return most_common[0]
    else:
        return "tie"

def get_classification_counts(statements):
    """Get counts of each classification type"""
    classifications = [s['classification'] for s in statements 
                      if s['classification'] is not None]
    return Counter(classifications)

def main():
    st.set_page_config(page_title="Diplomatic Speech Evaluation", layout="wide")
    
    # Initialize session state
    if 'evaluation_mode' not in st.session_state:
        st.session_state.evaluation_mode = None
    if 'current_sample' not in st.session_state:
        st.session_state.current_sample = []
    if 'current_index' not in st.session_state:
        st.session_state.current_index = 0
    if 'session_started' not in st.session_state:
        st.session_state.session_started = False
    
    # Load data
    unified_data, metadata = load_unified_data()
    existing_evaluations = load_existing_evaluations()
    
    st.title("Diplomatic Speech Evaluation Interface")
    
    # Mode selection page
    if not st.session_state.session_started:
        st.header("Select Evaluation Mode")
        
        available_relationships = get_available_relationships(unified_data, existing_evaluations)
        st.write(f"Available relationships for evaluation: {len(available_relationships)}")
        st.write(f"Already evaluated: {len(existing_evaluations)}")
        
        mode = st.selectbox(
            "Choose evaluation mode:",
            ["", "random10", "random25", "random50"],
            index=0
        )
        
        if mode and st.button("Start Evaluation Session"):
            # Generate random sample
            sample_size = int(mode.replace("random", ""))
            if len(available_relationships) < sample_size:
                st.warning(f"Only {len(available_relationships)} relationships available, using all of them.")
                sample_size = len(available_relationships)
            
            if sample_size == 0:
                st.error("No relationships available for evaluation!")
                return
            
            st.session_state.current_sample = random.sample(available_relationships, sample_size)
            st.session_state.evaluation_mode = mode
            st.session_state.current_index = 0
            st.session_state.session_started = True
            st.rerun()
        
        return
    
    # Evaluation interface
    if st.session_state.session_started and st.session_state.current_sample:
        # Progress indicator
        total_items = len(st.session_state.current_sample)
        current_pos = st.session_state.current_index + 1
        
        st.subheader(f"Evaluation Progress: {current_pos} of {total_items}")
        st.progress(current_pos / total_items)
        
        # Get current relationship
        current_relationship_key = st.session_state.current_sample[st.session_state.current_index]
        relationship_data = unified_data[current_relationship_key]
        
        st.header(f"Analysis for: {current_relationship_key}")
        
        # Create two columns
        col1, col2 = st.columns(2)
        
        # Left column - Bilateral data (editable)
        with col1:
            st.subheader("Bilateral Analysis")
            
            if relationship_data['bilateral'] is not None:
                bilateral = relationship_data['bilateral']
                
                # Editable rhetorical move
                st.write("**Rhetorical Move:**")
                new_rhetorical_move = st.text_area(
                    "Edit rhetorical move:",
                    value=bilateral['rhetorical_move'],
                    height=100,
                    key=f"rhetorical_move_{current_relationship_key}"
                )
                
                # Editable full text
                st.write("**Full Text:**")
                new_full_text = st.text_area(
                    "Edit full text:",
                    value=bilateral['full_text'],
                    height=150,
                    key=f"full_text_{current_relationship_key}"
                )
                
                # Bilateral classification (new field)
                st.write("**Classification (Bilateral):**")
                default_classification = get_default_bilateral_classification(relationship_data['statements'])
                new_bilateral_classification = st.text_input(
                    "Edit bilateral classification:",
                    value=default_classification,
                    key=f"bilateral_classification_{current_relationship_key}"
                )
                
                # Tag management
                st.write("**Tags:**")
                
                # Initialize session state for added tags if not exists
                if f"added_tags_{current_relationship_key}" not in st.session_state:
                    st.session_state[f"added_tags_{current_relationship_key}"] = []
                
                # Handle existing tags
                kept_tags = []
                if bilateral['tags']:
                    st.write("Select tags to KEEP:")
                    for i, tag in enumerate(bilateral['tags']):
                        if st.checkbox(tag, value=True, key=f"tag_{i}_{current_relationship_key}"):
                            kept_tags.append(tag)
                
                # Add previously added tags from session state
                kept_tags.extend(st.session_state[f"added_tags_{current_relationship_key}"])
                
                # Add new tags
                st.write("**Add New Tags:**")
                new_tag_input = st.text_input("Enter new tag:", key=f"new_tag_{current_relationship_key}")
                
                if st.button("Add Tag", key=f"add_tag_btn_{current_relationship_key}") and new_tag_input.strip():
                    new_tag_clean = new_tag_input.strip()
                    if new_tag_clean not in kept_tags:  # Avoid duplicates
                        st.session_state[f"added_tags_{current_relationship_key}"].append(new_tag_clean)
                        st.success(f"Added tag: {new_tag_clean}")
                        st.rerun()  # Refresh to show the new tag
                    else:
                        st.warning("Tag already exists!")
                
                # Show current tag selection
                if kept_tags:
                    st.write("**Current tags:**")
                    for tag in kept_tags:
                        st.code(tag)
                else:
                    st.write("No tags selected")
                
            else:
                st.warning("No bilateral data available for this relationship")
                new_rhetorical_move = ""
                new_full_text = ""
                new_bilateral_classification = get_default_bilateral_classification(relationship_data['statements'])
                kept_tags = []
        
        # Right column - Statement data (read-only for now)
        with col2:
            st.subheader("Individual Statements")
            
            statements = relationship_data['statements']
            
            if statements:
                st.write(f"**Number of statements: {len(statements)}**")
                
                # Classification summary
                classification_counts = get_classification_counts(statements)
                if classification_counts:
                    st.write("**Classification Summary:**")
                    for classification, count in classification_counts.most_common():
                        st.write(f"• {classification}: {count}")
                else:
                    st.write("**Classification Summary:** No classifications available")
                
                st.markdown("---")
                
                for i, statement in enumerate(statements):
                    with st.expander(f"Statement {i+1}: {statement['chunk_id']}"):
                        st.write(f"**Doc ID:** {statement['doc_id']}")
                        st.write(f"**Classification:** {statement['classification']}")
                        st.write(f"**Text:**")
                        st.write(statement['text'])
            else:
                st.warning("No statements available for this relationship")
        
        # Navigation and export buttons
        st.markdown("---")
        col_nav1, col_nav2, col_nav3 = st.columns([1, 1, 1])
        
        with col_nav1:
            if st.button("Previous", disabled=(st.session_state.current_index == 0)):
                st.session_state.current_index -= 1
                st.rerun()
        
        with col_nav2:
            if st.button("Export & Next", type="primary"):
                # Prepare evaluated data
                evaluated_data = {
                    'bilateral': {
                        'rhetorical_move': new_rhetorical_move,
                        'full_text': new_full_text,
                        'classification_bilateral': new_bilateral_classification,
                        'tags': kept_tags
                    },
                    'statements': relationship_data['statements']
                }
                
                # Save evaluation
                save_evaluation(current_relationship_key, evaluated_data, st.session_state.evaluation_mode)
                
                # Clear added tags for this relationship from session state
                if f"added_tags_{current_relationship_key}" in st.session_state:
                    del st.session_state[f"added_tags_{current_relationship_key}"]
                
                # Move to next or finish
                if st.session_state.current_index < len(st.session_state.current_sample) - 1:
                    st.session_state.current_index += 1
                    st.success("Evaluation saved! Moving to next relationship.")
                    st.rerun()
                else:
                    st.success("Evaluation session completed!")
                    st.session_state.session_started = False
                    st.session_state.current_sample = []
                    st.session_state.current_index = 0
                    st.rerun()
        
        with col_nav3:
            if st.button("Next (Skip)", disabled=(st.session_state.current_index >= len(st.session_state.current_sample) - 1)):
                st.session_state.current_index += 1
                st.rerun()
        
        # Session controls
        st.markdown("---")
        if st.button("End Session", type="secondary"):
            st.session_state.session_started = False
            st.session_state.current_sample = []
            st.session_state.current_index = 0
            st.rerun()

if __name__ == "__main__":
    main()