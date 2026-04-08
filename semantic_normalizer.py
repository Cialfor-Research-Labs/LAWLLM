import json
import logging
import re
from typing import List, Dict, Any
from case_model import Event
from llama_legal_answer import call_llm

logger = logging.getLogger(__name__)

CANONICAL_TAGS = [
    "money_not_paid", "money_not_returned", "cheque_bounce", "product_defective",
    "service_not_delivered", "unauthorized_access", "account_compromised", "possession_removed",
    "forced_exit", "threat_made", "false_statement_made", "data_privacy_threat",
    "harassment", "fraud_signal", "employment_ended", "overtime_work",
    "maternity_leave_request", "gratuity_dispute", "pf_dispute", "pf_not_contributed", "bonus_not_paid", "injury_at_work",
    "under_payment", "agreement_signal_present"
]

EVENT_TYPES = ["action", "state", "threat", "outcome"]

class SemanticNormalizer:
    """Bridges the gap between raw natural language and rigid legal primitives."""
    
    def __init__(self, model_name: str = "mistral.ministral-3-14b-instruct"):
        self.model_name = model_name

    def normalize_events(self, events: List[Event]) -> List[Event]:
        if not events:
            return []
            
        print(f"[SEMANTIC] Normalizing {len(events)} events...")
        
        # We batch the events into a single prompt for efficiency
        events_data = [
            {"seq": e.sequence, "desc": e.description, "action": e.action}
            for e in events
        ]
        
        tags_str = ", ".join(CANONICAL_TAGS)
        types_str = ", ".join(EVENT_TYPES)
        
        # Convert Pydantic objects to dicts for serialization
        events_dicts = [e.model_dump() for e in events]
        
        prompt = (
            "TASK: Normalize raw event descriptions into canonical legal behavior tags.\n"
            f"CANONICAL TAGS: {tags_str}\n"
            f"EVENT TYPES: {types_str}\n\n"
            "RULES:\n"
            "1. For each event, identify the most applicable canonical tag(s).\n"
            "2. Map 'failed to disburse', 'withheld', 'refused pay' -> money_not_paid.\n"
            "3. Map 'gratuity', 'retirement benefit' -> gratuity_dispute.\n"
            "4. Map 'PF', 'Provident Fund', 'EPF' -> pf_dispute.\n"
            "5. Map 'returned cheque', 'dishonored' -> cheque_bounce.\n"
            "6. Map 'broken', 'not working', 'defective', 'wrong product' -> product_defective.\n"
            "7. Map 'did not cool', 'failed to complete task', 'not fixed' -> service_not_delivered.\n"
            "8. Map 'hacked', 'logged in without permission', 'unauthorized access' -> unauthorized_access.\n"
            "9. Map 'threatened', 'abused', 'harassed' -> harassment.\n"
            "10. Map 'lie', 'deceived', 'fake profile', 'misrepresented', 'illegal charge' -> fraud_signal.\n"
            "9. Identify the type: 'action' (movement), 'state' (status/fact), 'threat' (future), 'outcome' (result/failure).\n"
            "10. Return ONLY a JSON object where keys are the sequence numbers (as strings).\n\n"
            f"EVENTS TO NORMALIZE:\n{json.dumps(events_dicts, indent=2)}\n\n"
            "FORMAT:\n"
            '{\n  "1": {"type": "action", "tags": ["money_not_paid"]},\n  "2": {...}\n}'
        )
        
        try:
            raw_res = call_llm(model_name=self.model_name, prompt=prompt, temperature=0.0)
            normalization_map = self._extract_json(raw_res)
            
            # Map results back to events
            for event in events:
                seq_str = str(event.sequence)
                if seq_str in normalization_map:
                    data = normalization_map[seq_str]
                    event.event_type = data.get("type", "action")
                    # Filter tags to ensure only canonical ones are used
                    tags = data.get("tags", [])
                    event.semantic_tags = [t for t in tags if t in CANONICAL_TAGS]
                    
            return events
        except Exception as e:
            logger.error(f"Semantic Normalization failed: {e}")
            return events

    def _extract_json(self, text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        # Find the first { and attempt to find the matching }
        start = cleaned.find("{")
        if start == -1:
            return json.loads(cleaned)
            
        # Basic brace counting to find the FIRST complete JSON block
        count = 0
        end = -1
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                count += 1
            elif cleaned[i] == "}":
                count -= 1
                if count == 0:
                    end = i
                    break
        
        if end != -1:
            content = cleaned[start:end+1]
            try:
                # Sanitize content (remove escaped newlines if any)
                content = content.replace('\\n', ' ')
                return json.loads(content)
            except json.JSONDecodeError:
                # Fallback to the original method if counting failed for some reason
                pass
                
        # Final fallback
        return json.loads(cleaned)
