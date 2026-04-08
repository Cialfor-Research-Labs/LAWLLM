import json
import os
import sys
from typing import List, Dict, Any

# Add parent directory to path to import local modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llama_legal_answer import call_llm
from legal_engine.models import (
    ExpandedIntent, ReasoningPlan, RetrievalResult, 
    Draft, Ground, Citation
)

DRAFTING_PROMPT = """You are an expert Indian Solicitor.
Using the provided facts, reasoning plan, and retrieved legal snippets (with snippet_ids), draft a structured legal analysis in JSON.

INPUTS:
- Facts: {facts_json}
- Reasoning Plan: {reasoning_json}
- Retrieval Results: {retrieval_json}

GUIDELINES:
- facts: A concise narrative of the key facts.
- issues: A list of primary and secondary legal issues addressed.
- grounds: A list of legal grounds. For each, specify the 'legal_basis' and a list of 'snippet_ids' used.
- analysis: A logical application of law to facts.
- prayer: The specifically requested relief or action.
- additional_remedies: Any ancillary reliefs possible.
- citations: A list of citations used in the grounds, each containing 'snippet_id', 'source_name', and 'section_or_citation'.
- domains_covered: list of legal domains addressed (e.g., consumer, criminal).

CONSTRAINTS:
- Use ONLY the provided snippets for legal bases. Do not invent law.
- Use the actual snippet_ids (e.g., S_consumer_1) for citations.
- Return ONLY valid JSON matching the Draft schema.

JSON OUTPUT:"""

def draft_output(
    intent: ExpandedIntent,
    reasoning: ReasoningPlan,
    retrieval_results: List[RetrievalResult],
    model: str = "llama3.1:8b",
    timeout: int = 180
) -> Draft:
    retrieval_json = json.dumps([r.model_dump() for r in retrieval_results], indent=2)
    
    prompt = DRAFTING_PROMPT.format(
        facts_json=intent.model_dump_json(indent=2),
        reasoning_json=reasoning.model_dump_json(indent=2),
        retrieval_json=retrieval_json
    )
    
    response_text = call_llm(
model=model, prompt=prompt, timeout_sec=timeout)
    
    try:
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            return Draft(**data)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"Error parsing Draft JSON: {e}")
        raise
