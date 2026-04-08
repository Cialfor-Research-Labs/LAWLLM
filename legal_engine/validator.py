import json
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import (
    Draft, IssueExpansion, DomainRoutingDecision, 
    ValidationResult
)

VALIDATION_PROMPT = """You are a Legal Quality Auditor.
Verify if the generated draft covers all identified legal issues and domains.

INPUTS:
- Draft: {draft_json}
- Issues Identified: {issues_json}
- Domains Selected: {domains_json}

CHECKS REQUIRED:
- Domain coverage: Are all 'domains_selected' mentioned in the draft?
- Issue coverage: Are all issues from 'issues' addressed in the analysis?
- Injury coverage: If physical injury was an issue, is compensation discussed?
- Evidence: Is evidence discussed if needed?

OUTPUT FORMAT:
Return ONLY a valid JSON object matching the ValidationResult schema.

JSON OUTPUT:"""

def validate_draft(
    draft: Draft,
    issues: IssueExpansion,
    routing: DomainRoutingDecision,
    model: str = "llama3.1:8b",
    timeout: int = 60
) -> ValidationResult:
    prompt = VALIDATION_PROMPT.format(
        draft_json=draft.model_dump_json(indent=2),
        issues_json=issues.model_dump_json(indent=2),
        domains_json=routing.model_dump_json(indent=2)
    )
    
    response_text = call_llm(
model=model, prompt=prompt, timeout_sec=timeout)
    
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return ValidationResult(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"Error parsing Validation JSON: {e}")
        raise
