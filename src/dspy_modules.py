from typing import List
from conversation_manager import ConversationManager, AnalysisEntry
from data_loader import SpeechData
from response_parser import ResponseParser


class DiplomaticAnalysisPipeline:
    def __init__(self, cohere_client):
        self.cohere_client = cohere_client
        self.conversation_manager = ConversationManager()
        
    def load_prompts(self) -> dict:
        prompts = {}
        prompt_files = {
            'system_initialization': 'prompts/system_initialization.md',
            'speech_analysis': 'prompts/speech_analysis.md',
            'typology_synthesis': 'prompts/typology_synthesis.md'
        }
        
        for key, filepath in prompt_files.items():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompts[key] = f.read().strip()
            except FileNotFoundError:
                print(f"Warning: {filepath} not found, using default prompt")
                prompts[key] = self._get_default_prompt(key)
        
        return prompts
    
    def _get_default_prompt(self, prompt_type: str) -> str:
        defaults = {
            'system_initialization': """You are an expert diplomatic speech analyst. Analyze speeches using <REASONING> and <ANALYSIS> tags.""",
            'speech_analysis': """Analyze this speech: {speech_text}\n\nCountry: {country}, Year: {year}\nSpeech #{speech_number}\n\nContext: {context}""",
            'typology_synthesis': """Create typologies of self-characterization and other-characterization patterns from all analyses."""
        }
        return defaults.get(prompt_type, "")
    
    def _analyze_single_speech(self, system_prompt: str, context: str, speech_prompt: str) -> str:
        """Analyze a single speech using the Cohere client directly"""
        full_prompt = f"""{system_prompt}

{context}

{speech_prompt}

Please provide your analysis using the required XML structure:
<REASONING>
[Your step-by-step thinking process]
</REASONING>

<ANALYSIS>
[Your structured analysis]
</ANALYSIS>"""
        
        return self.cohere_client.generate_response(full_prompt)
    
    def _generate_typology(self, system_prompt: str, conversation_history: str, synthesis_prompt: str) -> str:
        """Generate the final typology using the Cohere client directly"""
        full_prompt = f"""{system_prompt}

{conversation_history}

{synthesis_prompt}

Please provide your typology synthesis using the required XML structure:
<REASONING>
[Your step-by-step thinking process]
</REASONING>

<ANALYSIS>
[Your final typology with self-characterization and other-characterization types]
</ANALYSIS>"""
        
        return self.cohere_client.generate_response(full_prompt)
    
    def analyze_speech_batches(self, speech_batches: List[List[SpeechData]]) -> str:
        prompts = self.load_prompts()
        system_prompt = prompts['system_initialization']
        
        total_speeches = sum(len(batch) for batch in speech_batches)
        print(f"Starting analysis of {total_speeches} speeches in {len(speech_batches)} batches...")
        
        speech_counter = 0
        
        for batch_num, batch in enumerate(speech_batches, 1):
            print(f"\nProcessing batch {batch_num}/{len(speech_batches)} ({len(batch)} speeches)")
            
            for speech in batch:
                speech_counter += 1
                print(f"Analyzing speech {speech_counter}/{total_speeches}: {speech.country} ({speech.year})")
                
                context = self.conversation_manager.get_context_for_speech(speech_counter)
                
                speech_prompt = prompts['speech_analysis'].format(
                    speech_text=speech.content,
                    country=speech.country,
                    year=speech.year,
                    speech_number=speech_counter,
                    context=context
                )
                
                try:
                    response = self._analyze_single_speech(
                        system_prompt=system_prompt,
                        context=context,
                        speech_prompt=speech_prompt
                    )
                    
                    reasoning, analysis = ResponseParser.parse_xml_response(response)
                    
                    if not reasoning or not analysis:
                        print(f"Warning: Invalid response format for speech {speech_counter}")
                        reasoning = reasoning or "No reasoning provided"
                        analysis = analysis or response
                    
                    entry = AnalysisEntry(
                        speech_number=speech_counter,
                        country=speech.country,
                        year=speech.year,
                        content=speech.content,
                        reasoning=reasoning,
                        analysis=analysis
                    )
                    
                    self.conversation_manager.add_analysis(entry)
                    
                except Exception as e:
                    print(f"Error analyzing speech {speech_counter}: {e}")
                    continue
        
        print("\nGenerating final typology...")
        return self._generate_final_typology(prompts)
    
    def _generate_final_typology(self, prompts: dict) -> str:
        conversation_history = self.conversation_manager.get_full_conversation()
        
        try:
            result = self._generate_typology(
                system_prompt=prompts['system_initialization'],
                conversation_history=conversation_history,
                synthesis_prompt=prompts['typology_synthesis']
            )
            
            return result
            
        except Exception as e:
            print(f"Error generating typology: {e}")
            return "Error generating final typology"
    
    def analyze_speeches(self, speeches: List[SpeechData]) -> str:
        """Legacy method for backward compatibility"""
        return self.analyze_speech_batches([speeches])
    
    def get_full_conversation(self) -> str:
        return self.conversation_manager.get_full_conversation()