import json
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from law_engine import LawEngineResponse
from signal_registry import get_signals_for_tag, SignalDefinition

logger = logging.getLogger(__name__)

class InteractiveQuestion(BaseModel):
    id: str
    question: str
    options: List[str]
    source_tag: str

class InteractionResponse(BaseModel):
    results: LawEngineResponse
    question: Optional[InteractiveQuestion] = None
    message: str = "Results calculated."

class InteractiveSolver:
    """Manages the UI flow for 'improving accuracy' via smart questions."""
    
    def __init__(self, log_path: str = "interaction_logs.jsonl"):
        self.log_path = log_path

    def process_result(self, res: LawEngineResponse) -> InteractionResponse:
        # Task 6: DO NOT interrupt, show results first, then refine
        if not res.uncertainty or not res.uncertainty.is_uncertain:
            return InteractionResponse(results=res)

        # Task 3: Generate Question from Missing Signals
        question = self._generate_question(res)
        
        msg = "Initial results found. Improving accuracy with 1 smart question..."
        return InteractionResponse(
            results=res,
            question=question,
            message=msg
        )

    def _generate_question(self, res: LawEngineResponse) -> Optional[InteractiveQuestion]:
        if not res.uncertainty or not res.uncertainty.missing_signals:
            return None
            
        target_signal = res.uncertainty.missing_signals[0]
        
        # Find which tag is asking for this signal
        for tag in res.uncertainty.top_tags:
            sig_defs = get_signals_for_tag(tag)
            for s in sig_defs:
                if s.signal_name == target_signal:
                    return InteractiveQuestion(
                        id=s.signal_name,
                        question=s.question,
                        options=[opt.label for opt in s.options],
                        source_tag=tag
                    )
        return None

    def log_interaction(self, 
                       initial_tags: List[str], 
                       question: str, 
                       answer: str, 
                       final_tags: List[str], 
                       law_changed: bool):
        """Task 7: Store training data for future automation."""
        log_entry = {
            "timestamp": "@timestamp", # Placeholder
            "initial_tags": initial_tags,
            "question_asked": question,
            "user_answer": answer,
            "final_tags": final_tags,
            "law_changed": law_changed
        }
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")
