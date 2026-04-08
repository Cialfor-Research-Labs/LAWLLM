import json
import os
import sys

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import ExpandedIntent, IssueExpansion, ConversationState, QuestionPlan

QUESTION_PLAN_PROMPT = """You are a legal intake specialist.
Based on the current expanded intent and identified legal issues, generate a QuestionPlan JSON.

INPUTS:
- Expanded Intent: {intent_json}
- Identified Issues: {issues_json}
- Already Asked: {asked_fields}
- Answered Facts: {answered_facts}

GUIDELINES:
- Identify missing fields that are CRITICAL for the identified issues (e.g., if product liability is an issue, we need injury details and product brand/model).
- Generate up to 3 natural-language questions to fill these gaps.
- Each question MUST have a field_id matching the structure in ExpandedIntent (e.g., "harm.physical_injury_details", "product_or_service.brand").
- Do NOT ask questions for fields already in 'asked_fields' or 'answered_facts'.
- Set priority (1 is highest).
- Determine the stop_condition (enough_for_reasoning|user_refuses|max_turns_reached).

OUTPUT FORMAT:
Return ONLY a valid JSON object matching the QuestionPlan schema.

JSON OUTPUT:"""

def plan_questions(state: ConversationState, model: str = "llama3.1:8b", timeout: int = 60) -> QuestionPlan:
    intent_json = state.expanded_intent.model_dump_json(indent=2) if state.expanded_intent else "{}"
    issues_json = state.issues.model_dump_json(indent=2) if state.issues else "{}"
    
    prompt = QUESTION_PLAN_PROMPT.format(
        intent_json=intent_json,
        issues_json=issues_json,
        asked_fields=json.dumps(state.asked_fields),
        answered_facts=json.dumps(state.answered_fields)
    )
    
    response_text = call_llm(
model=model, prompt=prompt, timeout_sec=timeout)
    
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return QuestionPlan(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"Error parsing Question Plan JSON: {e}")
        raise
