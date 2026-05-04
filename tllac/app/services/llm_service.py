"""
LLM Service
=============
Generates structured legal responses from matched trained data.

Currently uses local template-based generation.
Can be extended to call a controlled LLM (e.g. via Ollama or Bedrock)
by injecting the system prompt + context as messages.
"""

from typing import Dict
import logging

from ..utils.prompt_builder import get_system_prompt

logger = logging.getLogger("tllac.services.llm")

# ──────────────────────────────────────────────
# Response Formatter (Template-based)
# ──────────────────────────────────────────────
def _format_template_response(matched_data: Dict) -> str:
    """
    Build a structured response following the system prompt format:
      - Title
      - Short Summary
      - Key Legal Points
      - (Optional) Relevant Act / Section
    """
    title = matched_data.get("title", "Legal Overview")
    summary = matched_data.get("summary", "No summary available.")
    points = matched_data.get("points", [])
    law = matched_data.get("law", "")
    case_refs = matched_data.get("case_references", [])
    practical = matched_data.get("practical_notes", "")

    # Build the response
    lines = [
        f"🔎 {title}",
        "",
        "**Summary:**",
        summary,
        "",
        "**Key Legal Points:**",
    ]

    for point in points:
        lines.append(f"• {point}")

    if law:
        lines.append("")
        lines.append("**Relevant Law:**")
        lines.append(f"• {law}")

    if case_refs:
        lines.append("")
        lines.append("**Landmark Cases:**")
        for case in case_refs:
            lines.append(f"• {case}")

    if practical:
        lines.append("")
        lines.append("**Practical Note:**")
        lines.append(practical)

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
def generate_response(query: str, matched_data: Dict) -> str:
    """
    Generate a response for the given query using matched trained data.

    The system prompt is loaded (for future LLM integration) and the
    matched data is formatted into a structured answer.
    """
    # Load system prompt (ready for future LLM call)
    _system_prompt = get_system_prompt()

    # Currently: template-based generation
    response = _format_template_response(matched_data)

    logger.info(
        "Generated response for topic '%s' (%d chars).",
        matched_data.get("matched_key", "unknown"),
        len(response),
    )
    return response
