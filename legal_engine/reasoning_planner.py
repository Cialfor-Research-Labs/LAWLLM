import json
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import (
    ExpandedIntent, IssueExpansion, RetrievalResult, 
    ReasoningPlan
)

REASONING_PLAN_PROMPT = """You are a senior Indian advocate (Advocate-on-Record).
Your task is to generate a comprehensive legal reasoning plan and strategy from the facts and law provided.

INPUTS:
- Expanded Intent: {intent_json}
- Identified Issues: {issues_json}
- Answered Facts: {answered_facts}
- Retrieved Law Snippets: {retrieval_json}

GUIDELINES:
- issue_map: Create a mapping of issues to their legal viability.
- recommended_actions: List specific procedural steps (e.g., "Send legal notice via registered post", "File FIR at nearest Police Station", "Approach District Consumer Forum").
- remedies: List all statutory and compensatory reliefs possible (e.g., "Refund", "Punitive damages", "FIR for negligence").
- evidence_needed: List documents and facts the user must produce to succeed.
- tone: Suggest the desired tone for documentation (e.g., "firm_formal", "conciliatory", "assertive").
- priority_level: Assess urgency (low, medium, high).

OUTPUT FORMAT:
Return ONLY a valid JSON object matching the ReasoningPlan schema.

JSON OUTPUT:"""

def plan_reasoning(
    intent: ExpandedIntent,
    issues: IssueExpansion,
    retrieval_results: List[RetrievalResult],
    answered_fields: Dict[str, Any],
    model: str = "llama3.1:8b",
    timeout: int = 120
) -> ReasoningPlan:
    retrieval_json = json.dumps([r.model_dump() for r in retrieval_results], indent=2)
    
    prompt = REASONING_PLAN_PROMPT.format(
        intent_json=intent.model_dump_json(indent=2),
        issues_json=issues.model_dump_json(indent=2),
        answered_facts=json.dumps(answered_fields),
        retrieval_json=retrieval_json
    )
    
    response_text = call_llm(model=model, prompt=prompt, timeout_sec=timeout)
    
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return ReasoningPlan(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"Error parsing Reasoning Plan JSON: {e}")
        raise
