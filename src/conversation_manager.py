from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class AnalysisEntry:
    speech_number: int
    country: str
    year: str
    content: str
    reasoning: str
    analysis: str
    patterns_identified: str = ""


class ConversationManager:
    def __init__(self):
        self.conversation_history: List[AnalysisEntry] = []
        self.accumulated_patterns: List[str] = []
    
    def add_analysis(self, entry: AnalysisEntry):
        self.conversation_history.append(entry)
        self._extract_patterns(entry)
    
    def _extract_patterns(self, entry: AnalysisEntry):
        if "pattern" in entry.analysis.lower() or "type" in entry.analysis.lower():
            pattern_summary = f"{entry.country} ({entry.year}): Key characterization patterns identified"
            self.accumulated_patterns.append(pattern_summary)
    
    def get_context_for_speech(self, speech_number: int) -> str:
        if speech_number == 1:
            return "This is the first speech in our analysis."
        
        context = f"Previous speeches analyzed: {len(self.conversation_history)}\n\n"
        context += "Key patterns identified so far:\n"
        
        # Show patterns from last 3 speeches for context
        for i, entry in enumerate(self.conversation_history[-3:], 1):
            context += f"- {entry.country} ({entry.year}): {self._summarize_analysis(entry.analysis)}\n"
        
        if self.accumulated_patterns:
            context += f"\nEmerging pattern themes: {len(self.accumulated_patterns)} distinct patterns observed\n"
        
        # Add batch context if we have multiple speeches
        if len(self.conversation_history) > 0:
            context += f"\nWe are building cumulative understanding across speeches. "
            context += f"Look for how this speech confirms, extends, or challenges the patterns we're developing.\n"
        
        return context
    
    def _summarize_analysis(self, analysis: str) -> str:
        lines = analysis.split('\n')[:3]
        summary = ' '.join(lines).replace('#', '').strip()
        return summary[:150] + "..." if len(summary) > 150 else summary
    
    def get_full_conversation(self) -> str:
        conversation = "# Complete Diplomatic Speech Analysis Conversation\n\n"
        
        for entry in self.conversation_history:
            conversation += f"## Speech {entry.speech_number}: {entry.country} ({entry.year})\n\n"
            conversation += f"### Reasoning\n{entry.reasoning}\n\n"
            conversation += f"### Analysis\n{entry.analysis}\n\n"
            conversation += "---\n\n"
        
        return conversation
    
    def get_all_analyses(self) -> List[AnalysisEntry]:
        return self.conversation_history
        if self.accumulated_patterns:
            context += f"\nEmerging pattern themes: {len(self.accumulated_patterns)} distinct patterns observed\n"
        
        return context
    
    def _summarize_analysis(self, analysis: str) -> str:
        lines = analysis.split('\n')[:3]
        summary = ' '.join(lines).replace('#', '').strip()
        return summary[:150] + "..." if len(summary) > 150 else summary
    
    def get_full_conversation(self) -> str:
        conversation = "# Complete Diplomatic Speech Analysis Conversation\n\n"
        
        for entry in self.conversation_history:
            conversation += f"## Speech {entry.speech_number}: {entry.country} ({entry.year})\n\n"
            conversation += f"### Reasoning\n{entry.reasoning}\n\n"
            conversation += f"### Analysis\n{entry.analysis}\n\n"
            conversation += "---\n\n"
        
        return conversation
    
    def get_all_analyses(self) -> List[AnalysisEntry]:
        return self.conversation_history