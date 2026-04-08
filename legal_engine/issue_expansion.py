import json
import os
import sys

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import ExpandedIntent, IssueExpansion

ISSUE_EXPANSION_PROMPT = """You are a senior Indian legal analyst.
Your task is to identify ALL plausible legal issues from the provided expanded intent.

CHECKLIST CATEGORIES:
- Consumer dispute (e.g., deficiency in service, unfair trade practice)
- Product liability (e.g., injury caused by defect)
- Contract breach (e.g., non-delivery, warranty violation)
- Tort / negligence (e.g., duty of care, damages)
- Criminal negligence (e.g., endangering life, causing hurt)
- Regulatory violations (e.g., safety standards)

GUIDELINES:
- For each plausible issue, assign an issue_id (e.g., I1, I2).
- Label and categorize clearly.
- Provide a brief description and a relevance_score (0.0 to 1.0).
- Mark the overall_severity (low, medium, high).
- Determine if needs_deep_reasoning (usually true if severity is medium/high).

OUTPUT FORMAT:
Return ONLY a valid JSON object matching the IssueExpansion schema.

EXPANDED INTENT:
{intent_json}

JSON OUTPUT:"""

def expand_issues(intent: ExpandedIntent, model: str = "llama3.1:8b", timeout: int = 60) -> IssueExpansion:
    intent_json = intent.model_dump_json(indent=2)
    prompt = ISSUE_EXPANSION_PROMPT.format(intent_json=intent_json)
    
    response_text = call_llm(
model=model, prompt=prompt, timeout_sec=timeout)
    
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return IssueExpansion(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"Error parsing Issue Expansion JSON: {e}")
        raise
