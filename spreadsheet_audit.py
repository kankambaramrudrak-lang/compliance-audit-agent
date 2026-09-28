"""CSV/XLSX loading and deterministic rules for the Audit Data page."""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd


ALIASES = {
    "control_id": ("control id", "control ref", "control reference", "control number"),
    "name": ("control", "control name", "control title", "name"),
    "domain": ("domain", "category", "control domain"),
    "requirement": ("requirement", "compliance requirement", "policy requirement", "criteria"),
    "evidence": ("evidence", "evidence provided", "evidence link", "artifact", "documentation"),
    "status": ("status", "compliance status", "result", "outcome", "assessment"),
    "owner": ("owner", "control owner", "action owner", "assignee"),
    "deadline": ("deadline", "due date", "target date", "action due date"),
    "action": ("action", "corrective action", "remediation", "remediation action"),
    "action_status": ("action status", "remediation status", "task status"),
    "test_status": ("test status", "testing status", "tested", "last tested", "test date"),
    "finding": ("finding", "finding description", "observation", "issue"),
    "risk": ("risk", "risk level", "severity"),
    "notes": ("notes", "comment", "comments", "auditor notes"),
}

PASS_VALUES = {"compliant", "pass", "passed", "effective", "implemented", "complete", "completed"}
FAIL_VALUES = {
    "non compliant", "noncompliant", "fail", "failed", "gap", "not compliant",
    "ineffective", "open", "not started", "pending", "in progress", "partial",
    "partially compliant",
}
INSUFFICIENT_VALUES = {"insufficient evidence", "inconclusive", "not enough evidence"}
REVIEW_VALUES = INSUFFICIENT_VALUES | {"needs review", "review required", "review"}
UNTESTED_VALUES = {"untested", "not tested", "never tested", "not started", "pending test"}
RECURRING_VALUES = {"recurring", "recurring finding", "repeat finding", "repeat"}
CLOSED_VALUES = {"closed", "complete", "completed", "done", "resolved"}
NEGATIVE_EVIDENCE = re.compile(
    r"\b(missing|not implemented|not in place|not met|failed|overdue|no evidence|"
    r"without evidence|gap found|ineffective|weak)\b",
    re.IGNORECASE,
)
POSITIVE_EVIDENCE = re.compile(
    r"\b(fully implemented|compliant|no issues|passed|effective control)\b",
    re.IGNORECASE,
)
HISTORICAL_ISSUE = re.compile(
    r"\b(non[\s-]?compliant|non[\s-]?compliance|compliance\s+gap|"
    r"gap(?:s)?\s+(?:identified|found|reported|observed)|"
    r"fail(?:ed|ure)\s+(?:the\s+)?(?:control|test|requirement)|"
    r"insufficient\s+evidence|missing\s+evidence|evidence\s+(?:was\s+)?not\s+(?:provided|attached)|"
    r"open\s+(?:corrective\s+)?actions?|(?:corrective\s+)?actions?\s+(?:remain(?:ed)?|are|were)\s+open|"
    r"unresolved\s+(?:issues?|actions?)|overdue\s+(?:remediation|actions?)|"
    r"remediation\s+(?:is\s+)?incomplete|previous\s+(?:finding|issue|gap)|"
    r"prior\s+(?:finding|issue|gap)|historical\s+(?:finding|issue|gap))\b",
    re.IGNORECASE,
)
NEGATED_HISTORICAL_ISSUE = re.compile(
    r"\b(?:no|not|without)\s+(?:any\s+)?(?:known\s+|identified\s+|reported\s+|material\s+)?"
    r"(?:compliance\s+)?(?:gaps?|issues?|findings?|open\s+actions?|unresolved\s+actions?)\b",
    re.IGNORECASE,
)
ISSUE_STATUS = re.compile(
    r"\b(?:finding|compliance|control)\s+status\s*:\s*"
    r"(?:non[\s-]?compliant|gap|failed?|insufficient\s+evidence|needs?\s+review|"
    r"untested|open|in\s+progress|blocked|overdue|pending|not\s+started)\b",
    re.IGNORECASE,
)
OPEN_ACTION_STATUS = re.compile(
    r"\b(?:corrective\s+action\s+status|action\s+status|status)\s*:\s*"
    r"(?:open|in\s+progress|blocked|overdue|pending|not\s+started)\b",
    re.IGNORECASE,
)


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def field_value(row: dict[str, Any], field: str) -> Any:
    for column, value in row.items():
        if normalize(column) in ALIASES[field]:
            return value
    return None


def has_field(dataframe: pd.DataFrame, field: str) -> bool:
    """Check whether the source file actually contains a recognized field."""
    return any(normalize(column) in ALIASES[field] for column in dataframe.columns)


def _memory_indicates_prior_issue(memory: str) -> bool:
    """Require explicit issue language from recalled history, not a topic mention."""
    text = memory or ""
    without_explicit_negations = NEGATED_HISTORICAL_ISSUE.sub(" ", text)
    return bool(
        ISSUE_STATUS.search(text)
        or OPEN_ACTION_STATUS.search(text)
        or HISTORICAL_ISSUE.search(without_explicit_negations)
    )


def text_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_audit_file(file_name: str, content: bytes) -> pd.DataFrame:
    """Load CSV or the first worksheet of an XLSX workbook."""
    extension = file_name.lower().rsplit(".", 1)[-1]
    if extension == "csv":
        try:
            return pd.read_csv(BytesIO(content), encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(BytesIO(content), encoding="latin-1")
    if extension == "xlsx":
        return pd.read_excel(BytesIO(content), engine="openpyxl")
    raise ValueError("Upload a CSV or .xlsx workbook.")


def dataframe_from_controls(controls: list[dict[str, Any]]) -> pd.DataFrame:
    """Adapt the existing Acme controls into the same tabular upload workflow."""
    return pd.DataFrame(
        [
            {
                "Control ID": control["id"],
                "Control": control["name"],
                "Domain": control["domain"],
                "Requirement": control["requirement"],
                "Evidence": control["evidence"],
                "Status": control["outcome"],
                "Owner": control["owner"],
                "Test status": "Tested",
            }
            for control in controls
        ]
    )


def _matches_history(
    organization: str,
    control_id: str,
    name: str,
    requirement: str,
    memories: list[str],
) -> str:
    organization_key = normalize(organization)
    control_id_key = normalize(control_id)
    name_key = normalize(name)
    requirement_tokens = [word for word in normalize(requirement).split() if len(word) > 3]
    for memory in memories:
        memory_key = normalize(memory)
        if organization_key not in memory_key:
            continue
        matches_control = bool(
            control_id_key and f" {control_id_key} " in f" {memory_key} "
        )
        matches_requirement = bool(
            requirement_tokens
            and sum(token in memory_key for token in requirement_tokens)
            >= min(3, len(requirement_tokens))
        )

        # Keep the issue evidence local to the matched control/requirement. A
        # recalled memory may summarize several controls, so an issue for one
        # must not make every other mentioned control look recurring.
        relevant_text = ""
        if matches_control:
            control_pattern = re.compile(
                rf"\bControl\s+(?:ID\s*[:#]?\s*)?{re.escape(control_id)}\b",
                re.IGNORECASE,
            )
            control_match = control_pattern.search(memory)
            if control_match:
                next_control = re.search(
                    r"\bControl\s+(?:ID\s*[:#]?\s*)?[A-Z][A-Z0-9_-]*\b",
                    memory[control_match.end():],
                    re.IGNORECASE,
                )
                end = control_match.end() + next_control.start() if next_control else len(memory)
                relevant_text = memory[control_match.start():end]
            else:
                # Some memory formats name the control without a "Control" label.
                id_pattern = re.compile(rf"\b{re.escape(control_id)}\b", re.IGNORECASE)
                id_match = id_pattern.search(memory)
                if id_match:
                    relevant_text = memory[id_match.start():]
        elif matches_requirement:
            # Only accept an explicitly labeled requirement section when the
            # control ID is absent from the memory.
            requirement_match = re.search(r"\b(?:requirement|criteria)\s*:\s*", memory, re.IGNORECASE)
            if requirement_match:
                relevant_text = memory[requirement_match.start():]

        if relevant_text and _memory_indicates_prior_issue(relevant_text):
            return memory
    return ""


def analyze_audit_dataframe(
    dataframe: pd.DataFrame,
    organization: str,
    audit_id: str,
    prior_memories: list[str] | None = None,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return row reviews and findings using fixed, explainable spreadsheet rules.

    Findings use the same keys as the current Audit Review page so they can
    flow directly into Findings & Actions and its existing Hindsight retain call.
    """
    today = today or date.today()
    prior_memories = prior_memories or []
    has_owner_column = has_field(dataframe, "owner")
    has_deadline_column = has_field(dataframe, "deadline")
    has_action_status_column = has_field(dataframe, "action_status")
    reviews: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for index, raw in dataframe.iterrows():
        row = raw.to_dict()
        row_number = int(index) + 2
        control_id = text_value(field_value(row, "control_id"))
        supplied_name = text_value(field_value(row, "name"))
        name = supplied_name or control_id or f"Spreadsheet row {row_number}"
        source_control_id = control_id or f"ROW-{row_number:04d}"
        requirement = text_value(field_value(row, "requirement"))
        evidence = text_value(field_value(row, "evidence"))
        source_finding = text_value(field_value(row, "finding"))
        risk = text_value(field_value(row, "risk"))
        notes = text_value(field_value(row, "notes"))
        source_status = text_value(field_value(row, "status"))
        owner = text_value(field_value(row, "owner"))
        source_deadline = text_value(field_value(row, "deadline"))
        action = text_value(field_value(row, "action"))
        action_status = text_value(field_value(row, "action_status"))
        test_status = text_value(field_value(row, "test_status"))
        domain = text_value(field_value(row, "domain")) or "Spreadsheet audit"
        status_key = normalize(source_status)
        exceptions: list[str] = []
        explanations: list[str] = []

        if (not supplied_name and not control_id) or not requirement:
            exceptions.append("Incomplete information")
            explanations.append("The control name or compliance requirement is missing.")

        if not evidence:
            exceptions.append("Missing evidence")
            explanations.append("No evidence was provided for this control.")

        if status_key in FAIL_VALUES:
            exceptions.append("Compliance gap")
            explanations.append(f"The recorded status '{source_status}' indicates the requirement is not met.")
        elif status_key in REVIEW_VALUES:
            exceptions.append("Review required")
            explanations.append("The recorded status indicates that the available evidence is insufficient.")
        elif status_key in UNTESTED_VALUES:
            exceptions.append("Untested control")
            explanations.append("The control is explicitly marked as untested.")
        elif not status_key:
            exceptions.append("Incomplete information")
            explanations.append("No compliance status was recorded.")
        elif status_key not in PASS_VALUES and status_key not in RECURRING_VALUES:
            exceptions.append("Incomplete information")
            explanations.append(f"The status '{source_status}' is not recognized by the deterministic audit rules.")

        if test_status and normalize(test_status) in UNTESTED_VALUES:
            if "Untested control" not in exceptions:
                exceptions.append("Untested control")
            explanations.append(f"The recorded test status is '{test_status}'.")

        parsed_deadline = pd.to_datetime(source_deadline, errors="coerce") if source_deadline else pd.NaT
        valid_action_deadline = bool(action) and not pd.isna(parsed_deadline)
        deadline = parsed_deadline.date().isoformat() if valid_action_deadline else ""
        if action:
            missing_action_details = []
            if has_owner_column and not owner:
                missing_action_details.append("owner")
            if has_deadline_column and not valid_action_deadline:
                missing_action_details.append("deadline")
            if has_action_status_column and not action_status:
                missing_action_details.append("status")
            if missing_action_details:
                exceptions.append("Incomplete information")
                explanations.append("The corrective action is missing " + ", ".join(missing_action_details) + ".")
        elif action_status:
            exceptions.append("Incomplete information")
            explanations.append("A corrective-action status is present but its action description is missing.")

        if valid_action_deadline and parsed_deadline.date() < today and normalize(action_status) not in CLOSED_VALUES:
            exceptions.append("Overdue action")
            explanations.append(
                f"The action deadline ({parsed_deadline.date().isoformat()}) has passed and the action is not closed."
            )

        if status_key in PASS_VALUES and NEGATIVE_EVIDENCE.search(evidence):
            exceptions.append("Inconsistent information")
            explanations.append("The status says the control passed, but the evidence text describes a gap.")
        elif status_key in FAIL_VALUES and POSITIVE_EVIDENCE.search(evidence):
            exceptions.append("Inconsistent information")
            explanations.append("The status indicates a gap, but the evidence text says the control is effective.")

        historical_context = _matches_history(
            organization, source_control_id, name, requirement, prior_memories
        )
        source_recurring = status_key in RECURRING_VALUES
        recurring = bool(historical_context) or source_recurring
        if recurring:
            exceptions.append("Recurring finding")
            if historical_context:
                explanations.append("Hindsight recalled a previous finding for this control or requirement.")
            elif source_recurring:
                explanations.append("The uploaded status marks this control as a recurring finding.")

        if any(
            issue in exceptions
            for issue in ("Compliance gap", "Overdue action", "Inconsistent information")
        ):
            result = "Non-compliant"
        elif any(
            issue in exceptions
            for issue in ("Missing evidence", "Incomplete information", "Untested control", "Review required")
        ):
            result = "Insufficient Evidence"
        elif status_key in FAIL_VALUES:
            result = "Non-compliant"
        elif source_recurring:
            result = "Insufficient Evidence"
        elif recurring and status_key not in PASS_VALUES:
            result = "Insufficient Evidence"
        else:
            result = "Compliant"

        days_to_deadline = (
            (parsed_deadline.date() - today).days if valid_action_deadline else 14
        )
        if source_finding:
            explanations.insert(0, f"Finding in export: {source_finding}")
        explanation = " ".join(dict.fromkeys(explanations)) or (
            "The row includes a requirement, evidence, and a passing status with no detected exception."
        )
        finding = {
            "id": f"{source_control_id}-ROW-{row_number:04d}",
            "control_id": source_control_id,
            "name": name,
            "domain": domain,
            "requirement": requirement,
            "evidence": evidence,
            "finding": source_finding,
            "risk": risk,
            "notes": notes,
            "status": result,
            "outcome": result,
            "exceptions": exceptions,
            "explanation": explanation,
            "owner": owner or "Unassigned",
            "days": days_to_deadline,
            "deadline": deadline,
            "action": action,
            "action_status": action_status,
            "recurring": recurring,
            "historical_context": historical_context,
            "organization": organization,
            "audit_id": audit_id,
            "source_row": row_number,
        }
        reviews.append(finding)
        if exceptions:
            findings.append(finding)

    return reviews, findings
