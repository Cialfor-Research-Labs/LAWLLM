"""
Response generation for the trained Indian legal chat backend.

Responses are built strictly from the matched dataset entry.
"""

from typing import Dict, List
import logging
import re

from ..utils.prompt_builder import get_system_prompt

logger = logging.getLogger("tllac.services.llm")


def _extract_section_numbers(query: str) -> List[str]:
    return re.findall(r"\b\d+[a-z]?\b", query.lower())


def _pick_relevant_points(query: str, points: List[str]) -> List[str]:
    if not points:
        return []

    section_numbers = _extract_section_numbers(query)
    if section_numbers:
        matched = [
            point for point in points
            if any(number in point.lower() or f"section {number}" in point.lower() for number in section_numbers)
        ]
        if matched:
            return matched[:3]

    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored_points = []
    for point in points:
        point_words = set(re.findall(r"[a-z0-9]+", point.lower()))
        overlap = len(query_words & point_words)
        scored_points.append((overlap, point))

    scored_points.sort(key=lambda item: item[0], reverse=True)
    best = [point for score, point in scored_points if score > 0][:3]
    return best or points[:4]


def _format_template_response(query: str, matched_data: Dict) -> str:
    title = matched_data.get("title", "Indian Legal Overview")
    summary = matched_data.get("summary", "No summary available in trained data.")
    points = matched_data.get("points", []) or []
    law = matched_data.get("law", "")
    case_refs = matched_data.get("case_references", []) or []
    practical = matched_data.get("practical_notes", "")
    relevant_points = _pick_relevant_points(query, points)

    lines = [
        f"Indian Legal Context: {title}",
        "",
        f"Summary: {summary}",
    ]

    if relevant_points:
        lines.append("")
        lines.append("Key Points:")
        for point in relevant_points:
            lines.append(f"- {point}")

    if law:
        lines.append("")
        lines.append(f"Relevant Law: {law}")

    if case_refs:
        lines.append("")
        lines.append("Relevant Cases:")
        for case in case_refs[:2]:
            lines.append(f"- {case}")

    if practical:
        lines.append("")
        lines.append(f"Practical Note: {practical}")

    return "\n".join(lines)


def generate_response(query: str, matched_data: Dict) -> str:
    """
    Generate a response using only the matched trained-data record.
    """
    _system_prompt = get_system_prompt()
    response = _format_template_response(query, matched_data)

    logger.info(
        "Generated trained-data response for '%s' (%d chars).",
        matched_data.get("matched_key", "unknown"),
        len(response),
    )
    return response
