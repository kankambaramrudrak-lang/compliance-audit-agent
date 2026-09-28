"""Deterministic, traceable answers over recalled and local audit records."""

from __future__ import annotations

import re
from typing import Any


_LABELS = [
    "AI assessment (observation/recommendation only)",
    "AI assessment (recommendation)",
    "AI explanation",
    "Auditor decision (final)",
    "Resulting finding status",
    "Corrective action status",
    "Evidence description",
    "Evidence reference",
    "Evidence title",
    "Evidence date",
    "Finding status",
    "Corrective action",
    "Requirement",
    "Deadline",
    "Owner",
    "Evidence",
    "Finding",
    "Previous value",
    "New value",
    "Change",
    "Control/finding",
    "Source/action",
    "Date",
    "Audit",
]
_LABEL_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(label) for label in sorted(_LABELS, key=len, reverse=True)) + r"):"
    r"\s*(.*?)(?=\s+(?:" + "|".join(re.escape(label) for label in sorted(_LABELS, key=len, reverse=True)) + r"):\s*|$)",
    re.IGNORECASE | re.DOTALL,
)
_STOP_WORDS = {
    "about", "after", "also", "and", "are", "between", "from", "happened", "has", "which",
    "what", "when", "where", "who", "with", "was", "were", "this", "that", "the", "for",
    "previous", "audit", "finding", "control", "history", "organization",
}


def demo_context_records(
    prior_record: dict[str, Any],
    controls: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    evidence_verifications: list[dict[str, Any]] | None = None,
    change_history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build explicitly labeled Acme fixture and session records for cold-start answers."""
    control = next((item for item in controls if item["id"] == prior_record["control_id"]), None)
    prior_text = (
        f"Organization: Acme Technologies. Previous compliance audit {prior_record['audit_id']} "
        f"dated {prior_record['date']}. Control {prior_record['control_id']}: {prior_record['control_name']}. "
        f"Requirement: {prior_record['requirement']} Finding status: {prior_record['status']}. "
        f"Finding: {prior_record['finding']} Corrective action: {prior_record['action']} "
        f"Owner: {prior_record['owner']}. Deadline: {prior_record['deadline']}. "
        f"Corrective action status: {prior_record['action_status']}."
    )
    records = [{"source": "Acme Technologies demo prior-audit fixture (local)", "text": prior_text}]

    if control:
        records.append({
            "source": "Acme Technologies control fixture (local; not a recalled prior-audit record)",
            "text": (
                f"Organization: Acme Technologies. Current demo control baseline, not a completed follow-up audit. "
                f"Control {control['id']}: {control['name']}. Requirement: {control['requirement']} "
                f"Evidence: {control['evidence']} Finding status: {control['outcome']}. Finding: {control['explanation']}"
            ),
        })

    for finding in findings or []:
        records.append({
            "source": f"Current audit session finding ({finding.get('audit_id', 'audit ID unavailable')})",
            "text": (
                f"Audit {finding.get('audit_id', 'not specified')}. Control {finding.get('control_id', finding.get('id', ''))}: "
                f"{finding.get('name', '')}. Requirement: {finding.get('requirement', '')}. "
                f"Evidence: {finding.get('evidence', '')}. Finding status: {finding.get('status', '')}. "
                f"Finding: {finding.get('explanation', '')}."
            ),
        })

    for action in actions or []:
        records.append({
            "source": f"Current corrective-action session record ({action.get('audit_id', 'audit ID unavailable')})",
            "text": (
                f"Audit {action.get('audit_id', 'not specified')}. Control {action.get('control_id', action.get('finding_id', ''))}. "
                f"Corrective action: {action.get('description', '')}. Owner: {action.get('owner', '')}. "
                f"Deadline: {action.get('deadline', '')}. Corrective action status: {action.get('status', '')}."
            ),
        })

    for event in evidence_verifications or []:
        records.append({
            "source": f"Confirmed evidence verification ({event.get('verified_at', 'date unavailable')}; local session record)",
            "text": (
                f"Audit {event.get('audit_id', '')}. Control {event.get('control_id', '')}: {event.get('finding_name', '')}. "
                f"Requirement: {event.get('requirement', '')}. Evidence title: {event.get('evidence_title', '')}. "
                f"Evidence description: {event.get('evidence_description', '')}. Evidence date: {event.get('evidence_date', '')}. "
                f"AI assessment (observation/recommendation only): {event.get('ai_assessment', '')}. "
                f"Auditor decision (final): {event.get('auditor_decision', '')}. "
                f"Resulting finding status: {event.get('final_status', '')}. Owner: {event.get('owner', '')}."
            ),
        })

    for event in change_history or []:
        records.append({
            "source": "Change History (local session)",
            "text": (
                f"Audit {event.get('audit_id', '')}. Control/finding: {event.get('item', '')}. "
                f"Change: {event.get('change', '')}. Previous value: {event.get('previous_value', '')}. "
                f"New value: {event.get('new_value', '')}. Source/action: {event.get('source', '')}. "
                f"Date: {event.get('timestamp', '')}."
            ),
        })
    return records


def _tokens(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(word) > 2 and word not in _STOP_WORDS
    }


def _fields(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for label, value in _LABEL_PATTERN.findall(text or ""):
        cleaned = value.strip().rstrip(" .")
        if cleaned:
            result.setdefault(label.lower(), []).append(cleaned)
    return result


def _field_values(records: list[dict[str, str]], labels: tuple[str, ...]) -> list[tuple[str, str]]:
    values = []
    for record in records:
        fields = _fields(record["text"])
        for label in labels:
            for value in fields.get(label.lower(), []):
                pair = (value, record["source"])
                if pair not in values:
                    values.append(pair)
    return values


def answer_audit_question(
    question: str,
    recalled_memories: list[str],
    local_records: list[dict[str, str]],
) -> dict[str, Any]:
    """Create a small template answer while keeping facts, observations, and decisions separate."""
    recalled = [{"source": "Hindsight Cloud recall", "text": text} for text in recalled_memories if text.strip()]
    control_match = re.search(r"\b[A-Z][A-Z0-9]{1,}-\d{2,}\b", question.upper())
    all_records = recalled + local_records
    if control_match:
        control_id = control_match.group(0)
        matching = [record for record in all_records if control_id.lower() in record["text"].lower()]
        if "previous" in question.lower() and matching:
            historical = [
                record for record in matching
                if record["source"] == "Hindsight Cloud recall"
                or record["source"].startswith("Acme Technologies demo prior-audit fixture")
                or "Previous compliance audit" in record["text"]
            ]
            if historical:
                matching = historical
        if matching:
            relevant = matching
        else:
            relevant = []
    else:
        question_tokens = _tokens(question)
        scored = [
            (len(question_tokens & _tokens(record["text"])), index, record)
            for index, record in enumerate(all_records)
        ]
        relevant = [record for score, _, record in sorted(scored, key=lambda item: (-item[0], item[1])) if score]
        if relevant:
            best = len(question_tokens & _tokens(relevant[0]["text"]))
            relevant = [
                record for record in relevant
                if len(question_tokens & _tokens(record["text"])) >= max(1, best - 1)
            ][:8]

    q = question.lower()
    asks_decision = any(word in q for word in ("decision", "decide", "decided", "auditor"))
    if not relevant and asks_decision and not control_match and all_records:
        relevant = all_records[:8]

    if not relevant:
        if asks_decision:
            return {
                "answer": "No explicit auditor decision was found in the available audit records. Any AI assessment is only a recommendation and cannot be treated as the auditor’s decision.",
                "facts": [],
                "observation": "The requested decision is not available in the current records.",
                "ai_assessments": [],
                "auditor_decisions": [],
                "recalled": [],
                "local_records": [],
            }
        return {
            "answer": "I could not find a matching control or audit record in Hindsight recall or the available Acme/session records. Try including a control ID such as IR-02.",
            "facts": [],
            "observation": "No observation can be supported from the available records.",
            "ai_assessments": [],
            "auditor_decisions": [],
            "recalled": [],
            "local_records": [],
        }

    facts: list[tuple[str, str]] = []
    if asks_decision:
        facts = []
    elif any(word in q for word in ("owner", "responsible", "who")):
        facts += _field_values(relevant, ("owner",))
    elif any(word in q for word in ("action", "open", "left")):
        facts += _field_values(relevant, ("corrective action", "corrective action status", "deadline"))
    if any(word in q for word in ("evidence", "artifact", "proof")):
        facts += _field_values(relevant, ("evidence title", "evidence description", "evidence", "evidence date", "evidence reference"))
    if any(word in q for word in ("status", "happened", "finding", "result")):
        facts += _field_values(relevant, ("finding status", "resulting finding status", "finding"))
    if any(word in q for word in ("deadline", "due", "date")):
        facts += _field_values(relevant, ("deadline", "evidence date"))
    if any(word in q for word in ("changed", "change", "between", "decision")):
        facts += _field_values(relevant, ("previous value", "new value", "change"))
    facts = list(dict.fromkeys(facts))
    asks_evidence = any(word in q for word in ("evidence", "artifact", "proof"))
    if not facts and not asks_decision and not asks_evidence:
        facts = _field_values(relevant, (
            "finding status", "finding", "corrective action", "corrective action status", "owner", "deadline"
        ))

    decisions = _field_values(relevant, ("auditor decision (final)",))
    observations = []
    ai_assessments = _field_values(relevant, ("ai assessment (observation/recommendation only)", "ai assessment (recommendation)"))
    ids = {match.group(0).upper() for record in relevant for match in re.finditer(r"\bAUD-[A-Z0-9-]+\b", record["text"].upper())}
    if "recurr" in q:
        if len(ids) >= 2:
            observations.append(f"The matching control appears in {len(ids)} distinct audit records; this is a derived recurring-finding observation, not an auditor decision.")
        else:
            observations.append("The available matching records do not establish appearances in multiple distinct audits, so recurrence cannot be confirmed.")
    if any(word in q for word in ("changed", "change", "between")):
        statuses = _field_values(relevant, ("finding status", "resulting finding status"))
        unique_statuses = list(dict.fromkeys(value for value, _ in statuses))
        if len(unique_statuses) >= 2:
            observations.append("Recorded finding statuses differ across the selected records: " + " → ".join(unique_statuses) + ". This is a comparison of records, not a decision.")
        else:
            previous_values = _field_values(relevant, ("previous value",))
            new_values = _field_values(relevant, ("new value",))
            if previous_values and new_values:
                observations.append(
                    "Change History records " + "; ".join(
                        f"{previous[0]} → {new[0]}" for previous, new in zip(previous_values, new_values)
                    ) + ". This is a record comparison, not an auditor decision."
                )
            elif not observations:
                observations.append("The available records do not contain enough distinct audit states to identify a change between audits.")
    if not observations:
        observations.append("The facts above are copied from audit records. No additional conclusion is needed to answer this question.")

    if asks_decision:
        answer = (
            "The recorded auditor decision was: "
            + "; ".join(f"{value} (source: {source})" for value, source in decisions)
            if decisions
            else "No explicit auditor decision was found in the matching records. AI assessments remain recommendations, not decisions."
        )
    else:
        if asks_evidence and not facts:
            answer = "The matching previous-audit records do not contain an explicit evidence detail."
        else:
            answer = "Based on the available matching audit records: " + (
                "; ".join(f"{value} (source: {source})" for value, source in facts[:6])
                if facts else "no matching labeled fact was found."
            )
    return {
        "answer": answer,
        "facts": facts,
        "observation": " ".join(observations),
        "ai_assessments": ai_assessments,
        "auditor_decisions": decisions,
        "recalled": [record for record in relevant if record["source"] == "Hindsight Cloud recall"],
        "local_records": [record for record in relevant if record["source"] != "Hindsight Cloud recall"],
    }
