"""Small deterministic event helpers for the local audit change log."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any


def make_history_event(
    *,
    timestamp: str,
    item: str,
    change: str,
    previous_value: Any,
    new_value: Any,
    source: str,
    audit_id: str = "",
) -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "item": item,
        "change": change,
        "previous_value": "Not recorded" if previous_value in (None, "") else str(previous_value),
        "new_value": "Not recorded" if new_value in (None, "") else str(new_value),
        "source": source,
        "audit_id": audit_id,
    }


def seed_demo_history(prior_record: dict[str, Any]) -> list[dict[str, str]]:
    """Create useful startup history from the existing Acme prior-audit fixture."""
    audit_date = date.fromisoformat(prior_record["date"])
    timestamp = datetime.combine(audit_date, time(hour=9)).astimezone().isoformat(timespec="seconds")
    action_timestamp = datetime.combine(audit_date, time(hour=9, minute=5)).astimezone().isoformat(timespec="seconds")
    control = f"{prior_record['control_id']} · {prior_record['control_name']}"
    action = f"Corrective action for {prior_record['control_id']}"
    audit_id = prior_record["audit_id"]
    return [
        make_history_event(
            timestamp=timestamp,
            item=control,
            change="Control / finding status",
            previous_value="Not assessed",
            new_value=prior_record["status"],
            source=f"Prior audit finding recorded ({audit_id})",
            audit_id=audit_id,
        ),
        make_history_event(
            timestamp=action_timestamp,
            item=action,
            change="Owner",
            previous_value="Unassigned",
            new_value=prior_record["owner"],
            source="Prior audit corrective action",
            audit_id=audit_id,
        ),
        make_history_event(
            timestamp=action_timestamp,
            item=action,
            change="Deadline",
            previous_value="Not set",
            new_value=prior_record["deadline"],
            source="Prior audit corrective action",
            audit_id=audit_id,
        ),
        make_history_event(
            timestamp=action_timestamp,
            item=action,
            change="Corrective action status",
            previous_value="Open",
            new_value=prior_record["action_status"],
            source="Prior audit corrective action",
            audit_id=audit_id,
        ),
    ]


def finding_status_events(
    previous_findings: list[dict[str, Any]],
    current_findings: list[dict[str, Any]],
    *,
    timestamp: str,
    source: str,
) -> list[dict[str, str]]:
    """Return events for newly recorded or changed control/finding results."""
    previous_by_control = {
        str(item.get("control_id", item.get("id", ""))): item
        for item in previous_findings
    }
    events = []
    for finding in current_findings:
        control_id = str(finding.get("control_id", finding.get("id", "")))
        previous = previous_by_control.get(control_id, {})
        old_status = previous.get("status", "Not assessed")
        new_status = finding.get("status", "Not recorded")
        if old_status == new_status:
            continue
        events.append(
            make_history_event(
                timestamp=timestamp,
                item=f"{control_id} · {finding.get('name', control_id)}",
                change="Control / finding status",
                previous_value=old_status,
                new_value=new_status,
                source=source,
                audit_id=str(finding.get("audit_id", "")),
            )
        )
    return events
