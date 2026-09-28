"""Deterministic in-app deadline classification and reminder rows."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any


COMPLETED_STATUSES = {"closed", "complete", "completed", "done", "resolved"}


def parse_deadline(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def classify_deadline(
    deadline: Any,
    status: str,
    *,
    today: date | None = None,
    due_soon_days: int = 7,
) -> dict[str, Any]:
    today = today or date.today()
    if (status or "").strip().lower() in COMPLETED_STATUSES:
        return {"urgency": "Completed", "days_remaining": None}
    due_date = parse_deadline(deadline)
    if due_date is None:
        return {"urgency": "No deadline", "days_remaining": None}
    days_remaining = (due_date - today).days
    if days_remaining < 0:
        urgency = "Overdue"
    elif days_remaining <= due_soon_days:
        urgency = "Due soon"
    else:
        urgency = "Upcoming"
    return {"urgency": urgency, "days_remaining": days_remaining}


def build_reminder_items(
    *,
    saved_actions: list[dict[str, Any]],
    prior_action: dict[str, Any] | None,
    findings: list[dict[str, Any]],
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Combine demo, corrective-action, and spreadsheet deadlines into reminder rows."""
    finding_by_id = {str(item.get("id", "")): item for item in findings}
    finding_by_control = {str(item.get("control_id", item.get("id", ""))): item for item in findings}
    items: list[dict[str, Any]] = []

    def add_item(
        *,
        control_id: str,
        finding_name: str,
        action: str,
        owner: str,
        deadline: Any,
        status: str,
        audit_id: str,
        source: str,
        record: dict[str, Any],
        kind: str,
    ) -> None:
        classification = classify_deadline(deadline, status, today=today)
        identity = "|".join(
            [kind, audit_id, control_id, str(record.get("finding_id", record.get("id", ""))), action or ""]
        )
        items.append({
            "key": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12],
            "control_id": control_id or "Not specified",
            "finding": finding_name or control_id or "Audit follow-up",
            "action": action or "Audit follow-up",
            "owner": owner or "Unassigned",
            "deadline": parse_deadline(deadline).isoformat() if parse_deadline(deadline) else "",
            "status": status or "Open",
            "urgency": classification["urgency"],
            "days_remaining": classification["days_remaining"],
            "audit_id": audit_id,
            "source": source,
            "_record": record,
            "_kind": kind,
        })

    if prior_action:
        control_id = str(prior_action.get("control_id", ""))
        add_item(
            control_id=control_id,
            finding_name=prior_action.get("finding_name", ""),
            action=prior_action.get("description", ""),
            owner=prior_action.get("owner", ""),
            deadline=prior_action.get("deadline"),
            status=prior_action.get("status", "Open"),
            audit_id=prior_action.get("audit_id", ""),
            source="Acme prior-audit demo",
            record=prior_action,
            kind="prior_action",
        )

    for action in saved_actions:
        finding_id = str(action.get("finding_id", ""))
        finding = finding_by_id.get(finding_id, {})
        control_id = str(action.get("control_id") or finding.get("control_id", finding_id))
        finding = finding or finding_by_control.get(control_id, {})
        add_item(
            control_id=control_id,
            finding_name=finding.get("name", ""),
            action=action.get("description", ""),
            owner=action.get("owner", ""),
            deadline=action.get("deadline"),
            status=action.get("status", "Open"),
            audit_id=action.get("audit_id", finding.get("audit_id", "")),
            source="Findings & Actions",
            record=action,
            kind="saved_action",
        )

    for finding in findings:
        if not finding.get("action") and not finding.get("deadline"):
            continue
        control_id = str(finding.get("control_id", finding.get("id", "")))
        add_item(
            control_id=control_id,
            finding_name=finding.get("name", ""),
            action=finding.get("action", "Audit follow-up"),
            owner=finding.get("owner", ""),
            deadline=finding.get("deadline"),
            status=finding.get("action_status") or "Open",
            audit_id=finding.get("audit_id", ""),
            source="Uploaded audit data",
            record=finding,
            kind="finding_action",
        )
    return items
