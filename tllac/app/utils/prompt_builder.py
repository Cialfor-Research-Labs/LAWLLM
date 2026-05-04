"""
Prompt Builder
===============
Central location for the MANDATORY system prompt.
Used by llm_service.py to construct prompts for controlled LLM calls.
"""

from typing import Dict, Optional


def get_system_prompt() -> str:
    """Return the strict Indian Legal AI system prompt."""
    return """You are an AI Legal Assistant strictly trained on Indian Law.

RULES:

1. You must ONLY answer in the context of Indian legal system.
2. Do NOT provide global, US, UK, or generic legal answers.
3. If the question is unrelated to Indian law, respond with:
   "This is out of context"

4. If the answer is not found in your trained data, respond with:
   "This is not in my trained data"

5. Do NOT hallucinate.
6. Do NOT assume facts not present in trained data.
7. Keep answers structured and precise.

RESPONSE FORMAT:

- Title
- Short Summary
- Key Legal Points
- (Optional) Relevant Act / Section

If unsure → ALWAYS fallback to:
"This is not in my trained data"
"""


def build_full_prompt(
    query: str,
    matched_data: Optional[Dict] = None,
) -> str:
    """
    Build a complete prompt combining:
      1. System prompt
      2. Matched trained data context (if any)
      3. User query

    This is ready for use with any LLM API call.
    """
    prompt_parts = [get_system_prompt()]

    if matched_data:
        context_lines = [
            "--- TRAINED DATA CONTEXT ---",
            f"Topic: {matched_data.get('title', 'N/A')}",
            f"Summary: {matched_data.get('summary', 'N/A')}",
            f"Key Points: {', '.join(matched_data.get('points', []))}",
            f"Relevant Law: {matched_data.get('law', 'N/A')}",
        ]
        case_refs = matched_data.get("case_references", [])
        if case_refs:
            context_lines.append(f"Landmark Cases: {', '.join(case_refs)}")
        context_lines.append("--- END CONTEXT ---")
        prompt_parts.append("\n".join(context_lines))

    prompt_parts.append(f"USER QUERY: {query}")

    return "\n\n".join(prompt_parts)
