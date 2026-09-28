"""Deterministic evidence checks and Hindsight event formatting."""

from __future__ import annotations

import re
from typing import Any


_STOP_WORDS = {
    "about", "after", "against", "among", "and", "are", "for", "from", "into",
    "must", "shall", "that", "the", "their", "this", "through", "with", "within",
}


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def assess_evidence(
    requirement: str,
    title: str,
    description: str,
    evidence_date: str,
    reference: str = "",
) -> dict[str, str]:
    """Return a repeatable, advisory assessment based on completeness and relevance."""
    title = (title or "").strip()
    description = (description or "").strip()
    reference = (reference or "").strip()
    evidence_text = " ".join(part for part in (title, description, reference) if part)

    if not evidence_text:
        return {
            "assessment": "Missing",
            "explanation": "No evidence details or reference were provided for this requirement.",
        }

    requirement_tokens = _tokens(requirement)
    evidence_tokens = _tokens(evidence_text)
    overlap = requirement_tokens & evidence_tokens
    if not title or not description:
        return {
            "assessment": "Insufficient",
            "explanation": "A title and a description are both needed to assess relevance and what the evidence demonstrates.",
        }
    if not evidence_date:
        return {
            "assessment": "Insufficient",
            "explanation": "The evidence has no date, so its currency cannot be checked against the requirement.",
        }
    if len(description.split()) < 8:
        return {
            "assessment": "Insufficient",
            "explanation": "The description is too brief to show how the evidence meets the requirement.",
        }
    if requirement_tokens and len(overlap) < min(2, len(requirement_tokens)):
        return {
            "assessment": "Insufficient",
            "explanation": "The evidence is described, but its details do not clearly connect to the requirement.",
        }

    return {
        "assessment": "Supported",
        "explanation": "The dated evidence has a substantive description that refers to key parts of the requirement. Auditor review is still required.",
    }


def verification_memory_content(event: dict[str, Any]) -> str:
    """Build a memory that explicitly separates the advisory AI result and final decision."""
    return (
        f"Organization: {event['organization']}. Audit {event['audit_id']} evidence verification "
        f"dated {event['verified_at']}. Finding/control {event['control_id']}: {event['finding_name']}. "
        f"Requirement: {event['requirement']}. Evidence title: {event['evidence_title']}. "
        f"Evidence description: {event['evidence_description']}. Evidence date: {event['evidence_date']}. "
        f"Evidence reference: {event['evidence_reference'] or 'None supplied'}. "
        f"AI assessment (observation/recommendation only): {event['ai_assessment']}. "
        f"AI explanation: {event['ai_explanation']}. "
        f"Auditor decision (final): {event['auditor_decision']}. "
        f"Resulting finding status: {event['final_status']}. Owner: {event['owner'] or 'Unassigned'}."
    )
