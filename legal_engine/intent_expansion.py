import json
import os
import sys

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import ExpandedIntent

INTENT_EXPANSION_PROMPT = """You are an expert Indian legal intake assistant.
Your task is to convert raw user input into a structured ExpandedIntent JSON object.

GUIDELINES:
- case_summary: A concise 2-3 sentence summary of the facts.
- primary_issue: The most prominent legal concern (e.g., "Defective product", "Wrongful termination").
- secondary_issues: A list of other plausible legal concerns.
- legal_domains_guess: Categorize into ["consumer", "contract", "tort", "criminal", "labour", "family", "property"].
- facts: Extract structured data for:
    - parties (user_role, opposite_party_type, opposite_party_name)
    - timeline (incident_date, complaint_date)
    - money (claim_amount_inr, price_paid_inr)
    - harm (physical_injury, property_damage, mental_agony)
    - product_or_service (type, brand, model)
- missing_information: List specific details needed to provide better advice.
- risk_flags: List critical signals like "injury_present", "high_claim", "statute_of_limitations_near".
- confidence: Score from 0.0 to 1.0 based on how clear the input is.

OUTPUT FORMAT:
Return ONLY a valid JSON object matching the ExpandedIntent schema. Do not include any conversational filler.

USER INPUT:
{user_text}

JSON OUTPUT:"""

def expand_intent(user_text: str, model: str = "llama3.1:8b", timeout: int = 60) -> ExpandedIntent:
    prompt = INTENT_EXPANSION_PROMPT.format(user_text=user_text)
    
    response_text = call_llm(
model=model, prompt=prompt, timeout_sec=timeout)
    
    # Try to extract JSON if there's any filler (though prompt asks for ONLY JSON)
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return ExpandedIntent(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        # Fallback or re-raise
        print(f"Error parsing Intent Expansion JSON: {e}")
        # Return a minimal valid object or handle error
        raise
