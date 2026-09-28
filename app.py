from __future__ import annotations

import os
import time
from datetime import date, datetime
from uuid import uuid4

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from hindsight_client import Hindsight

from audit_data import BANK_ID, CONTROLS, ORGANIZATION, ORGANIZATION_ID, prior_audit_record
from spreadsheet_audit import (
    analyze_audit_dataframe,
    dataframe_from_controls,
    field_value,
    load_audit_file,
    text_value,
)
from evidence_verification import assess_evidence, verification_memory_content
from audit_history import finding_status_events, make_history_event, seed_demo_history
from reminders import build_reminder_items, classify_deadline, parse_deadline
from audit_assistant import answer_audit_question, demo_context_records


load_dotenv()
st.set_page_config(page_title="Hindsight | Audit Workspace", page_icon="◈", layout="wide")

STATUS_BADGE_COLORS = {
    "Compliant": "green",
    "Resolved": "green",
    "Under Review": "blue",
    "Closed": "green",
    "Non-compliant": "red",
    "Overdue": "red",
    "Blocked": "red",
    "Insufficient Evidence": "orange",
    "Open": "orange",
    "In progress": "blue",
    "Recurring finding": "blue",
}


def hindsight_client() -> Hindsight:
    api_key = os.getenv("HINDSIGHT_API_KEY")
    if not api_key:
        raise RuntimeError("HINDSIGHT_API_KEY is not set. Add it to the existing .env file and restart the app.")
    return Hindsight(base_url="https://api.hindsight.vectorize.io", api_key=api_key)


def memory_results_text(result) -> list[str]:
    return [str(item.text) for item in (getattr(result, "results", None) or []) if getattr(item, "text", None)]


def store_prior_audit(record: dict) -> None:
    content = (
        f"Organization: {ORGANIZATION} ({ORGANIZATION_ID}). Previous compliance audit {record['audit_id']} "
        f"dated {record['date']}. Control {record['control_id']}: {record['control_name']}. "
        f"Requirement: {record['requirement']} Finding status: {record['status']}. "
        f"Finding: {record['finding']} Corrective action: {record['action']} "
        f"Owner: {record['owner']}. Deadline: {record['deadline']}. "
        f"Corrective action status: {record['action_status']}. This is a prior audit record for future comparison."
    )
    hindsight_client().retain(
        bank_id=BANK_ID,
        content=content,
        context=f"Compliance audit history for {ORGANIZATION}",
        document_id=f"{ORGANIZATION_ID}-{record['audit_id']}-finding-{record['control_id']}",
        metadata={"organization": ORGANIZATION_ID, "audit_id": record["audit_id"], "control_id": record["control_id"]},
        tags=["compliance-audit", ORGANIZATION_ID, "finding", "corrective-action"],
    )


def recall_audit_history(query: str) -> list[str]:
    result = hindsight_client().recall(
        bank_id=BANK_ID,
        query=f"{ORGANIZATION} previous compliance audit {query}",
        max_tokens=1200,
    )
    return memory_results_text(result)


def store_corrective_action(finding: dict, action: dict) -> None:
    audit_id = finding.get("audit_id", st.session_state.audit_id)
    content = (
        f"Organization: {ORGANIZATION}. Follow-up audit {audit_id}, dated {date.today().isoformat()}. "
        f"Control {finding['id']}: {finding['name']}. Finding status: {finding['status']}. "
        f"Finding: {finding['explanation']} Corrective action: {action['description']} "
        f"Owner: {action['owner']}. Deadline: {action['deadline']}. Status: {action['status']}."
    )
    hindsight_client().retain(
        bank_id=BANK_ID,
        content=content,
        context=f"Compliance audit corrective action for {ORGANIZATION}",
        document_id=f"{ORGANIZATION_ID}-{audit_id}-{finding['id']}-action",
        metadata={"organization": ORGANIZATION_ID, "audit_id": audit_id, "control_id": finding["control_id"] if "control_id" in finding else finding["id"]},
        tags=["compliance-audit", ORGANIZATION_ID, "finding", "corrective-action"],
    )


def store_spreadsheet_finding(finding: dict) -> None:
    content = (
        f"Organization: {ORGANIZATION} ({ORGANIZATION_ID}). Uploaded audit {finding['audit_id']}. "
        f"Control {finding['control_id']}: {finding['name']}. Requirement: {finding['requirement']}. "
        f"Evidence: {finding['evidence'] or 'No evidence provided.'} Finding status: {finding['status']}. "
        f"Exceptions: {', '.join(finding['exceptions'])}. Finding: {finding['explanation']} "
        "This finding was detected during a spreadsheet audit and is retained for future comparison."
    )
    hindsight_client().retain(
        bank_id=BANK_ID,
        content=content,
        context=f"Spreadsheet compliance audit history for {ORGANIZATION}",
        document_id=f"{ORGANIZATION_ID}-{finding['audit_id']}-upload-{finding['id']}-finding",
        metadata={
            "organization": ORGANIZATION_ID,
            "audit_id": finding["audit_id"],
            "control_id": finding["control_id"],
        },
        tags=["compliance-audit", ORGANIZATION_ID, "finding", "spreadsheet-audit"],
    )


def store_evidence_verification(event: dict) -> None:
    """Retain an auditor-confirmed verification as organization audit memory."""
    hindsight_client().retain(
        bank_id=BANK_ID,
        content=verification_memory_content(event),
        context=f"Compliance evidence verification for {ORGANIZATION}",
        document_id=(
            f"{ORGANIZATION_ID}-{event['audit_id']}-{event['control_id']}-verification-{uuid4().hex}"
        ),
        metadata={
            "organization": ORGANIZATION_ID,
            "audit_id": event["audit_id"],
            "control_id": event["control_id"],
            "finding_id": event["finding_id"],
            "ai_assessment": event["ai_assessment"],
            "auditor_decision": event["auditor_decision"],
        },
        tags=["compliance-audit", ORGANIZATION_ID, "evidence-verification", "auditor-decision"],
    )


def show_status(status: str) -> None:
    st.badge(status, color=STATUS_BADGE_COLORS.get(status, "gray"))

if "prior_record" not in st.session_state:
    st.session_state.prior_record = prior_audit_record()
if "prior_stored" not in st.session_state:
    st.session_state.prior_stored = False
if "audit_findings" not in st.session_state:
    st.session_state.audit_findings = []
if "recalled_memories" not in st.session_state:
    st.session_state.recalled_memories = []
if "audit_id" not in st.session_state:
    st.session_state.audit_id = "AUD-2026-028"
if "saved_actions" not in st.session_state:
    st.session_state.saved_actions = []
if "prior_corrective_action" not in st.session_state:
    prior = st.session_state.prior_record
    st.session_state.prior_corrective_action = {
        "finding_id": prior["control_id"],
        "control_id": prior["control_id"],
        "finding_name": prior["control_name"],
        "description": prior["action"],
        "owner": prior["owner"],
        "deadline": prior["deadline"],
        "status": prior["action_status"],
        "audit_id": prior["audit_id"],
    }
if "evidence_verifications" not in st.session_state:
    st.session_state.evidence_verifications = []
if "audit_reviews" not in st.session_state:
    st.session_state.audit_reviews = []
if "audit_source" not in st.session_state:
    st.session_state.audit_source = "Acme Technologies demo controls"
if "audit_recall_warning" not in st.session_state:
    st.session_state.audit_recall_warning = ""
if "audit_retention_warnings" not in st.session_state:
    st.session_state.audit_retention_warnings = []
if "change_history" not in st.session_state:
    st.session_state.change_history = seed_demo_history(st.session_state.prior_record)


with st.sidebar:
    st.markdown("## ◈ Hindsight")
    st.caption("COMPLIANCE AUDIT WORKSPACE")
    if "workspace_page" not in st.session_state:
        st.session_state.workspace_page = "Dashboard"
    navigation_sections = {
        "Overview": ["Dashboard"],
        "Audit & controls": ["Audit Data", "Audit Review"],
        "Findings & actions": ["Findings & Actions", "Reminders"],
        "Evidence": ["Evidence Verification"],
        "History & intelligence": ["Change History", "AI Assistant", "Memory Trail"],
    }
    for section, pages in navigation_sections.items():
        st.caption(section.upper())
        for page_name in pages:
            if st.button(
                page_name,
                key=f"nav-{page_name}",
                type="primary" if st.session_state.workspace_page == page_name else "secondary",
                width="stretch",
            ):
                st.session_state.workspace_page = page_name
    page = st.session_state.workspace_page
    st.divider()
    st.caption("ORGANIZATION")
    st.markdown(f"**{ORGANIZATION}**")
    st.caption("HINDSIGHT MEMORY BANK")
    st.code(BANK_ID, language=None)
    st.caption("Hindsight Cloud retains and recalls audit history.")


def hero(kicker: str, title: str, subtitle: str) -> None:
    st.caption(kicker.upper())
    st.title(title)
    st.write(subtitle)


def record_history_change(
    item: str,
    change: str,
    previous_value: object,
    new_value: object,
    source: str,
    audit_id: str = "",
) -> None:
    st.session_state.change_history.append(
        make_history_event(
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            item=item,
            change=change,
            previous_value=previous_value,
            new_value=new_value,
            source=source,
            audit_id=audit_id,
        )
    )


def render_change_history() -> None:
    hero(
        "Local audit log",
        "Change History",
        "Chronological record of findings, corrective actions, evidence updates, and auditor decisions.",
    )
    events = sorted(
        st.session_state.change_history,
        key=lambda event: event["timestamp"],
        reverse=True,
    )
    st.caption(f"{len(events)} recorded changes · Includes seeded Acme Technologies prior audit history.")
    if events:
        with st.container(border=True):
            st.dataframe(
                pd.DataFrame(events)[
                    ["timestamp", "item", "change", "previous_value", "new_value", "source", "audit_id"]
                ].rename(
                    columns={
                        "timestamp": "Date/time",
                        "item": "Item / control",
                        "change": "What changed",
                        "previous_value": "Previous value",
                        "new_value": "New value",
                        "source": "Source / action",
                        "audit_id": "Audit",
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        with st.expander("Event timeline", expanded=False):
            for event in events:
                st.markdown(
                    f"**{event['timestamp']} · {event['item']}**  ·  {event['change']}  \n"
                    f"{event['previous_value']} → {event['new_value']}  \n"
                    f"*{event['source']} · {event['audit_id'] or 'Not specified'}*"
                )


def current_reminders() -> list[dict]:
    return build_reminder_items(
        saved_actions=st.session_state.saved_actions,
        prior_action=st.session_state.prior_corrective_action,
        findings=st.session_state.audit_findings,
    )


def render_reminders() -> None:
    hero(
        "In-app deadlines",
        "Reminders",
        "Track corrective-action due dates and audit follow-ups. Urgency updates automatically using today’s date.",
    )
    reminders = current_reminders()
    if not reminders:
        st.info("No action deadlines are recorded yet. Create a corrective action or upload audit data with action deadlines.")
        return

    urgency_colors = {
        "Overdue": "red",
        "Due soon": "orange",
        "Upcoming": "blue",
        "Completed": "green",
        "No deadline": "gray",
    }
    ordered = sorted(
        reminders,
        key=lambda item: (
            {"Overdue": 0, "Due soon": 1, "Upcoming": 2, "No deadline": 3, "Completed": 4}.get(item["urgency"], 5),
            item["days_remaining"] if item["days_remaining"] is not None else 999999,
        ),
    )
    urgency_counts = {
        label: sum(item["urgency"] == label for item in reminders)
        for label in ("Overdue", "Due soon", "Upcoming", "Completed")
    }
    with st.container(horizontal=True):
        st.metric("Overdue", urgency_counts["Overdue"], border=True)
        st.metric("Due soon", urgency_counts["Due soon"], border=True)
        st.metric("Upcoming", urgency_counts["Upcoming"], border=True)
        st.metric("Completed", urgency_counts["Completed"], border=True)
    st.caption("Deadlines within 7 days are Due soon. Completed actions are separated from open deadlines.")
    for item in ordered:
        with st.container(border=True):
            with st.expander("Change deadline"):
                with st.form(f"reminder-deadline-form-{item['key']}"):
                    default_deadline = parse_deadline(item["deadline"]) or date.today()
                    new_deadline = st.date_input(
                        "New deadline",
                        value=default_deadline,
                        key=f"reminder-deadline-{item['key']}",
                    )
                    changed = st.form_submit_button("Save deadline")
            if changed:
                old_deadline = item["deadline"] or "Not set"
                new_deadline_text = new_deadline.isoformat()
                if new_deadline_text == item["deadline"]:
                    st.info("The deadline is unchanged.")
                else:
                    item["_record"]["deadline"] = new_deadline_text
                    item["deadline"] = new_deadline_text
                    classification = classify_deadline(new_deadline_text, item["status"])
                    item["urgency"] = classification["urgency"]
                    item["days_remaining"] = classification["days_remaining"]
                    record_history_change(
                        f"Corrective action for {item['control_id']}",
                        "Deadline",
                        old_deadline,
                        new_deadline_text,
                        "Reminders · deadline updated",
                        item["audit_id"],
                    )
                    st.success("Deadline updated and added to Change History.")
            title_cols = st.columns([3, 1])
            title_cols[0].markdown(f"**{item['control_id']} · {item['finding']}**")
            title_cols[1].badge(item["urgency"], color=urgency_colors[item["urgency"]])
            st.write(item["action"])
            st.caption(
                f"Owner: {item['owner']} · Deadline: {item['deadline'] or 'Not set'} · "
                f"Status: {item['status']} · Audit: {item['audit_id'] or 'Not specified'} · {item['source']}"
            )

    refreshed = current_reminders()
    rows = [
        {
            "Control / finding": item["control_id"] + " · " + item["finding"],
            "Action": item["action"],
            "Owner": item["owner"],
            "Deadline": item["deadline"] or "Not set",
            "Status": item["status"],
            "Urgency": item["urgency"],
            "Audit": item["audit_id"] or "Not specified",
        }
        for item in refreshed
    ]
    with st.expander("Full deadline register"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_assistant_response(message: dict) -> None:
    result = message["result"]
    if message.get("recall_error"):
        st.warning(f"Hindsight recall was unavailable for this question: {message['recall_error']} Local Acme/session context is labeled separately below.")
    with st.container(border=True):
        st.markdown("**Answer from matching records**")
        st.write(result["answer"])

    st.markdown("**Recalled historical facts**")
    if result["facts"]:
        for fact, source in result["facts"]:
            st.markdown(f"- {fact}  \n  *Source: {source}*")
    else:
        st.caption("No matching labeled historical fact was found.")

    st.markdown("**AI-generated / derived observation (not an auditor decision)**")
    st.write(result["observation"])

    st.markdown("**Auditor decisions (explicitly recorded as final)**")
    if result["auditor_decisions"]:
        for decision, source in result["auditor_decisions"]:
            st.markdown(f"- {decision}  \n  *Source: {source}*")
    else:
        st.write("No explicit auditor decision was found in the matching records. AI assessments are recommendations and are not treated as decisions.")

    if result["ai_assessments"]:
        st.markdown("**AI assessment from evidence records (recommendation only)**")
        for assessment, source in result["ai_assessments"]:
            st.markdown(f"- {assessment}  \n  *Source: {source}*")

    with st.expander(f"Trace supporting this answer · {len(result['recalled'])} Hindsight record(s), {len(result['local_records'])} local record(s)"):
        st.markdown("**Recalled from Hindsight Cloud**")
        if result["recalled"]:
            for record in result["recalled"]:
                with st.container(border=True):
                    st.write(record["text"])
        else:
            st.caption("No relevant Hindsight memories were returned for this question.")
        st.markdown("**Local Acme fixture / current-session history**")
        if result["local_records"]:
            for record in result["local_records"]:
                with st.container(border=True):
                    st.caption(record["source"])
                    st.write(record["text"])
        else:
            st.caption("No local records were used for this answer.")


def render_ai_assistant() -> None:
    hero(
        "Audit history Q&A",
        "AI Assistant",
        "Audit copilot for organizational history. Questions search Hindsight Cloud first; deterministic answers include the records that support them.",
    )
    st.caption("Historical facts, derived observations, and explicit auditor decisions are shown separately. This prototype uses deterministic templates, not an LLM.")
    if "assistant_messages" not in st.session_state:
        st.session_state.assistant_messages = []

    st.markdown("**Suggested questions**")
    suggestions = [
        "What happened with IR-02 in the previous audit?",
        "Which findings are recurring?",
        "What actions are overdue?",
        "What changed since the previous audit?",
    ]
    suggested_question = None
    suggestion_cols = st.columns(2)
    for index, suggestion in enumerate(suggestions):
        if suggestion_cols[index % 2].button(
            suggestion,
            key=f"assistant-suggestion-{index}",
            width="stretch",
        ):
            suggested_question = suggestion

    for message in st.session_state.assistant_messages:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.write(message["content"])
            else:
                render_assistant_response(message)

    question = suggested_question or st.chat_input("Ask about a control, finding, evidence, owner, or auditor decision")
    if not question:
        return

    st.session_state.assistant_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    recall_error = ""
    recalled = []
    try:
        with st.spinner("Recalling relevant organization audit history from Hindsight Cloud..."):
            recalled = recall_audit_history(question)
    except Exception as exc:
        recall_error = str(exc)

    local_records = demo_context_records(
        st.session_state.prior_record,
        CONTROLS,
        findings=st.session_state.audit_findings,
        actions=[*st.session_state.saved_actions, st.session_state.prior_corrective_action],
        evidence_verifications=st.session_state.evidence_verifications,
        change_history=st.session_state.change_history,
    )
    result = answer_audit_question(question, recalled, local_records)
    assistant_message = {
        "role": "assistant",
        "result": result,
        "recall_error": recall_error,
    }
    st.session_state.assistant_messages.append(assistant_message)
    with st.chat_message("assistant"):
        render_assistant_response(assistant_message)


def render_audit_data() -> None:
    hero(
        "Spreadsheet review",
        "Audit Data",
        "Upload a control register or audit export. The first pass uses deterministic rules and the existing Hindsight audit bank.",
    )
    st.subheader("Upload")
    st.caption("CSV or Excel workbook (.xlsx) · Excel files use the first worksheet.")
    upload = st.file_uploader(
        "Upload audit data",
        type=["csv", "xlsx"],
        help="Upload a control register or audit export.",
    )
    if upload is None:
        st.info("No file uploaded. The existing Acme Technologies controls are available as demo data.")
        dataframe = dataframe_from_controls(CONTROLS)
        source = "Acme Technologies demo controls"
    else:
        try:
            dataframe = load_audit_file(upload.name, upload.getvalue())
            source = upload.name
        except Exception as exc:
            st.error(f"Could not read the uploaded file: {exc}")
            return
        if dataframe.empty:
            st.warning("The file has headers but no audit rows.")
            return

    st.subheader("Dataset preview", icon=":material/table_view:")
    st.caption(f"{len(dataframe):,} rows | {len(dataframe.columns):,} columns | {source}")
    st.dataframe(dataframe.head(100), hide_index=True)
    if len(dataframe) > 100:
        st.caption("Preview is limited to 100 rows. Analysis covers every row.")
    st.caption(
        "Recognized columns include Control ID, Control, Requirement, Evidence, Status, Owner, "
        "Deadline, Action, Action Status, and Test Status."
    )

    st.subheader("Analysis", icon=":material/fact_check:")
    st.caption("Deterministic rules check each row for gaps, evidence exceptions, and overdue actions.")
    if st.button("Analyze audit data", type="primary", icon=":material/analytics:"):
        controls_for_recall = []
        for _, row in dataframe.iterrows():
            record = row.to_dict()
            control_id = text_value(field_value(record, "control_id"))
            control_name = text_value(field_value(record, "name"))
            if control_id or control_name:
                controls_for_recall.append(f"{control_id} {control_name}".strip())
        recall_query = "uploaded spreadsheet controls " + "; ".join(dict.fromkeys(controls_for_recall))
        recall_warning = ""
        try:
            with st.spinner("Recalling prior audit findings from Hindsight Cloud..."):
                memories = recall_audit_history(recall_query[:1800])
        except Exception as exc:
            memories = []
            recall_warning = f"Hindsight recall was unavailable for this review: {exc}"

        audit_id = f"AUD-UPLOAD-{date.today().strftime('%Y%m%d')}-{int(time.time())}"
        reviews, _ = analyze_audit_dataframe(
            dataframe,
            ORGANIZATION,
            audit_id,
            prior_memories=memories,
        )
        st.session_state.change_history.extend(
            finding_status_events(
                st.session_state.audit_findings,
                reviews,
                timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
                source=f"Audit Data analysis ({source})",
            )
        )
        st.session_state.audit_id_upload = audit_id
        st.session_state.audit_reviews = reviews
        st.session_state.audit_findings = reviews
        st.session_state.audit_source = source
        st.session_state.recalled_memories = memories
        st.session_state.audit_recall_warning = recall_warning

        retention_warnings = []
        for finding in reviews:
            if finding["exceptions"]:
                try:
                    store_spreadsheet_finding(finding)
                except Exception as exc:
                    retention_warnings.append(
                        f"{finding['control_id']}: {exc}"
                    )
        st.session_state.audit_retention_warnings = retention_warnings
        st.success(
            f"Reviewed {len(reviews)} row(s) and recorded "
            f"{sum(bool(finding['exceptions']) for finding in reviews)} finding(s)."
        )

    if st.session_state.audit_reviews:
        if st.session_state.audit_recall_warning:
            st.warning(st.session_state.audit_recall_warning)
        if st.session_state.audit_retention_warnings:
            st.warning(
                "Some findings could not be retained in Hindsight. "
                + " | ".join(st.session_state.audit_retention_warnings[:3])
            )
        st.subheader("Exceptions and findings", icon=":material/assignment_late:")
        result_counts = {
            "Compliant": sum(finding["status"] == "Compliant" for finding in st.session_state.audit_reviews),
            "Non-compliant": sum(finding["status"] == "Non-compliant" for finding in st.session_state.audit_reviews),
            "Insufficient Evidence": sum(finding["status"] == "Insufficient Evidence" for finding in st.session_state.audit_reviews),
            "Recurring finding": sum(bool(finding.get("recurring")) for finding in st.session_state.audit_reviews),
        }
        with st.container(horizontal=True):
            st.metric("Compliant", result_counts["Compliant"])
            st.metric("Gaps", result_counts["Non-compliant"])
            st.metric("Evidence review", result_counts["Insufficient Evidence"])
            st.metric("Recurring", result_counts["Recurring finding"])
        result_rows = [
            {
                "Row": finding["source_row"],
                "Control ID": finding["control_id"],
                "Control": finding["name"],
                "Result": finding["status"],
                "Exceptions": ", ".join(finding["exceptions"]),
                "Explanation": finding["explanation"],
            }
            for finding in st.session_state.audit_reviews
        ]
        st.dataframe(pd.DataFrame(result_rows), hide_index=True)


def render_evidence_verification() -> None:
    hero(
        "Evidence verification",
        "Verify evidence against a finding",
        "Record evidence, review a deterministic AI observation, and confirm the final auditor decision.",
    )
    with st.container(horizontal=True):
        st.badge("01 · Requirement", color="gray")
        st.badge("02 · Evidence", color="blue")
        st.badge("03 · AI assessment", color="orange")
        st.badge("04 · Auditor decision", color="green")
    st.caption("The AI assessment is a recommendation. The auditor makes and records the final decision.")
    if not st.session_state.audit_findings:
        st.info("No findings are available yet. Run Audit Review or analyze audit data first. The Acme Technologies demo controls remain available in Audit Review.")
        return

    findings = st.session_state.audit_findings
    selected_id = st.selectbox(
        "Finding",
        [finding["id"] for finding in findings],
        format_func=lambda value: f"{value} · {next(f['name'] for f in findings if f['id'] == value)}",
    )
    finding = next(item for item in findings if item["id"] == selected_id)
    with st.container(border=True):
        st.markdown(f"**{finding.get('control_id', finding['id'])} · Requirement**")
        st.write(finding.get("requirement") or "No requirement was recorded for this finding.")

    with st.form("evidence-details-form"):
        st.markdown("**Evidence provided**")
        title = st.text_input("Evidence title/name", key="verification-title")
        description = st.text_area("Evidence description", key="verification-description")
        evidence_date = st.date_input("Evidence date", value=date.today(), key="verification-date")
        reference = st.text_input("Optional text/file reference", key="verification-reference", placeholder="Document name, ticket, URL, or file reference")
        assess_submitted = st.form_submit_button("Assess evidence", type="primary")

    if assess_submitted:
        assessment = assess_evidence(
            finding.get("requirement", ""), title, description, evidence_date.isoformat(), reference
        )
        st.session_state.evidence_assessment = {
            "finding_id": selected_id,
            "evidence_title": title.strip(),
            "evidence_description": description.strip(),
            "evidence_date": evidence_date.isoformat(),
            "evidence_reference": reference.strip(),
            **assessment,
        }

    draft = st.session_state.get("evidence_assessment")
    if draft and draft.get("finding_id") == selected_id:
        with st.container(border=True):
            st.markdown("**AI assessment · Recommendation**")
            st.badge(draft["assessment"], color={"Supported": "green", "Insufficient": "orange", "Missing": "red"}[draft["assessment"]])
            st.write(draft["explanation"])
            st.caption("Automated observation only. It is not an approval or final audit result.")
        decisions = {
            "Accept evidence / Resolved": ("Accept evidence", "Resolved", "Closed"),
            "Request more evidence / Under Review": ("Request more evidence", "Under Review", "In progress"),
            "Reject evidence / Remains Open": ("Reject evidence", "Open", "Open"),
        }
        st.subheader("Auditor decision", icon=":material/gavel:")
        st.caption("Choose and confirm the final disposition for this finding.")
        with st.form("auditor-decision-form", border=True):
            decision_label = st.selectbox("Auditor decision", list(decisions))
            confirm = st.form_submit_button("Confirm auditor decision", type="primary")
        if confirm:
            decision, final_status, action_status = decisions[decision_label]
            control_id = str(finding.get("control_id", selected_id))
            linked_actions = [
                item for item in st.session_state.saved_actions
                if item.get("finding_id") == selected_id or item.get("control_id") == control_id
            ]
            prior_action = st.session_state.prior_corrective_action
            if prior_action.get("control_id") == control_id:
                linked_actions.append(prior_action)
            action = next(
                (item for item in reversed(st.session_state.saved_actions) if item in linked_actions),
                prior_action if prior_action in linked_actions else None,
            )
            event = {
                "organization": ORGANIZATION,
                "audit_id": finding.get("audit_id", st.session_state.audit_id),
                "finding_id": selected_id,
                "control_id": finding.get("control_id", selected_id),
                "finding_name": finding.get("name", selected_id),
                "requirement": finding.get("requirement", ""),
                "evidence_title": draft["evidence_title"],
                "evidence_description": draft["evidence_description"],
                "evidence_date": draft["evidence_date"],
                "evidence_reference": draft["evidence_reference"],
                "ai_assessment": draft["assessment"],
                "ai_explanation": draft["explanation"],
                "auditor_decision": decision,
                "final_status": final_status,
                "owner": action.get("owner", finding.get("owner", "Unassigned")) if action else finding.get("owner", "Unassigned"),
                "verified_at": date.today().isoformat(),
            }
            try:
                with st.spinner("Recording auditor decision in Hindsight Cloud..."):
                    store_evidence_verification(event)
                previous_status = finding.get("status", "Not assessed")
                prior_verification = next(
                    (item for item in reversed(st.session_state.evidence_verifications) if item["finding_id"] == selected_id),
                    None,
                )
                previous_evidence = (
                    f"{prior_verification['evidence_title']} (dated {prior_verification['evidence_date']})"
                    if prior_verification
                    else finding.get("evidence") or "No verification evidence"
                )
                current_evidence = f"{event['evidence_title']} (dated {event['evidence_date']})"
                if event["evidence_reference"]:
                    current_evidence += f" · Reference: {event['evidence_reference']}"
                record_history_change(
                    f"{event['control_id']} · {event['finding_name']}",
                    "Evidence update",
                    previous_evidence,
                    current_evidence,
                    "Evidence Verification",
                    event["audit_id"],
                )
                record_history_change(
                    f"{event['control_id']} · {event['finding_name']}",
                    "AI assessment (recommendation)",
                    prior_verification["ai_assessment"] if prior_verification else "Not assessed",
                    f"{event['ai_assessment']}: {event['ai_explanation']}",
                    "Evidence Verification",
                    event["audit_id"],
                )
                record_history_change(
                    f"{event['control_id']} · {event['finding_name']}",
                    "Auditor decision",
                    prior_verification["auditor_decision"] if prior_verification else "Not decided",
                    event["auditor_decision"],
                    "Evidence Verification",
                    event["audit_id"],
                )
                record_history_change(
                    f"{event['control_id']} · {event['finding_name']}",
                    "Control / finding status",
                    previous_status,
                    final_status,
                    "Evidence Verification",
                    event["audit_id"],
                )
                for linked_action in linked_actions:
                    previous_action_status = linked_action.get("status", "Not recorded")
                    if previous_action_status != action_status:
                        record_history_change(
                            f"Corrective action for {event['control_id']}",
                            "Corrective action status",
                            previous_action_status,
                            action_status,
                            "Evidence Verification decision",
                            linked_action.get("audit_id", event["audit_id"]),
                        )
                    linked_action["status"] = action_status
                    linked_action["evidence_verification"] = decision
                finding["status"] = final_status
                finding["outcome"] = final_status
                st.session_state.evidence_verifications.append(event)
                st.session_state.recalled_memories.append(verification_memory_content(event))
                st.session_state.evidence_assessment = None
                st.success(f"Auditor decision recorded in Hindsight. Finding status: {final_status}.")
            except Exception as exc:
                st.error(f"The decision was not applied because Hindsight could not store its audit record: {exc}")

    history = [event for event in st.session_state.evidence_verifications if event["finding_id"] == selected_id]
    if history:
        st.subheader("Verification history")
        for event in reversed(history):
            with st.container(border=True):
                st.caption(f"{event['verified_at']} · Owner: {event['owner']}")
                st.write(f"AI assessment (recommendation): {event['ai_assessment']} — {event['ai_explanation']}")
                st.write(f"Auditor decision (final): {event['auditor_decision']} · Finding status: {event['final_status']}")


if page == "Dashboard":
    dashboard_records = st.session_state.audit_reviews or st.session_state.audit_findings
    if dashboard_records:
        dashboard_controls = [
            {
                "id": item.get("control_id", item.get("id", "Control")),
                "name": item.get("name", "Unnamed control"),
                "domain": item.get("domain", ""),
                "status": item.get("status", item.get("outcome", "Not assessed")),
                "explanation": item.get("explanation", ""),
                "owner": item.get("owner", "Unassigned"),
                "risk": item.get("risk", ""),
                "recurring": item.get("recurring", False),
            }
            for item in dashboard_records
        ]
        dashboard_audit = (
            st.session_state.get("audit_id_upload", st.session_state.audit_id)
            if st.session_state.audit_reviews else st.session_state.audit_id
        )
        dashboard_source = st.session_state.audit_source
    else:
        dashboard_controls = [
            {
                "id": item["id"],
                "name": item["name"],
                "domain": item["domain"],
                "status": item["outcome"],
                "explanation": item["explanation"],
                "owner": item["owner"],
                "risk": item.get("risk", ""),
                "recurring": item.get("previous_finding", False),
            }
            for item in CONTROLS
        ]
        dashboard_audit = st.session_state.audit_id
        dashboard_source = "Acme Technologies demo controls"

    total_controls = len(dashboard_controls)
    compliant_controls = sum(item["status"] == "Compliant" for item in dashboard_controls)
    attention_controls = [item for item in dashboard_controls if item["status"] != "Compliant"]
    recurring_controls = sum(bool(item.get("recurring")) for item in dashboard_controls)
    reminders = current_reminders()
    open_actions = [item for item in reminders if item["urgency"] != "Completed"]
    overdue_actions = [item for item in reminders if item["urgency"] == "Overdue"]

    st.caption(f"{ORGANIZATION}  ·  {dashboard_source}  ·  {date.today().strftime('%d %b %Y')}")
    st.title("Compliance command center", icon=":material/space_dashboard:")
    st.badge(dashboard_audit, color="blue", icon=":material/fact_check:")

    with st.container(horizontal=True):
        st.metric("Controls in scope", total_controls, border=True)
        st.metric(
            "Compliant",
            f"{(compliant_controls / total_controls * 100):.0f}%" if total_controls else "—",
            f"{compliant_controls} of {total_controls} controls",
            border=True,
        )
        st.metric("Open findings", len(attention_controls), border=True)
        st.metric("Overdue actions", len(overdue_actions), border=True)
        evidence_gap_count = sum(item["status"] == "Insufficient Evidence" for item in dashboard_controls)
        st.metric("Evidence gaps", evidence_gap_count, border=True)
        st.metric("Recurring findings", recurring_controls, border=True)

    attention_col, summary_col = st.columns([1.35, 1], gap="medium")
    with attention_col:
        st.subheader("Needs attention", icon=":material/priority_high:")
        if attention_controls:
            priority = {"Non-compliant": 0, "Insufficient Evidence": 1, "Under Review": 2}
            attention_controls.sort(key=lambda item: priority.get(item["status"], 3))
            for item in attention_controls[:4]:
                with st.container(border=True):
                    item_col, status_col = st.columns([3.2, 1])
                    item_col.markdown(f"**{item['id']}  ·  {item['name']}**")
                    item_col.caption(
                        f"{item['domain']}  ·  Owner: {item['owner']}  ·  "
                        f"Risk: {item['risk'] or 'Not recorded'}"
                    )
                    with status_col:
                        show_status(item["status"])
                    if item["explanation"]:
                        st.caption(item["explanation"])
            if len(attention_controls) > 4:
                st.caption(f"{len(attention_controls) - 4} more controls need attention in Audit Review.")
        else:
            st.success("All assessed controls are compliant.")

    with summary_col:
        st.subheader("Compliance & risk", icon=":material/monitoring:")
        with st.container(border=True):
            st.markdown("**Control posture**")
            st.progress(compliant_controls / total_controls if total_controls else 0.0)
            st.caption(f"{compliant_controls} compliant  ·  {len(attention_controls)} requiring follow-up")
            st.divider()
            gap_count = sum(item["status"] == "Non-compliant" for item in dashboard_controls)
            evidence_count = sum(item["status"] == "Insufficient Evidence" for item in dashboard_controls)
            recurring_count = recurring_controls
            risk_cols = st.columns(3)
            risk_cols[0].metric("Gaps", gap_count)
            risk_cols[1].metric("Evidence", evidence_count)
            risk_cols[2].metric("Recurring", recurring_count)
            st.caption("Counts reflect the active audit dataset.")

    deadlines_col, activity_col = st.columns([1, 1], gap="medium")
    with deadlines_col:
        st.subheader("Upcoming deadlines", icon=":material/event_upcoming:")
        if open_actions:
            urgency_order = {"Overdue": 0, "Due soon": 1, "Upcoming": 2, "No deadline": 3}
            open_actions.sort(key=lambda item: (urgency_order.get(item["urgency"], 4), item["deadline"] or "9999"))
            for item in open_actions[:3]:
                with st.container(border=True):
                    st.markdown(f"**{item['control_id']}  ·  {item['finding']}**")
                    st.caption(item["action"])
                    urgency_color = {"Overdue": "red", "Due soon": "orange", "Upcoming": "blue"}.get(item["urgency"], "gray")
                    st.badge(
                        f"{item['urgency']}  ·  {item['deadline'] or 'No date'}",
                        color=urgency_color,
                    )
                    st.caption(f"Owner: {item['owner']}  ·  {item['status']}")
        else:
            st.success("No open corrective actions.")

    with activity_col:
        st.subheader("Recent audit activity", icon=":material/history:")
        recent_events = sorted(
            st.session_state.change_history,
            key=lambda event: event.get("timestamp", ""),
            reverse=True,
        )[:4]
        if recent_events:
            for event in recent_events:
                with st.container(border=True):
                    try:
                        event_date = datetime.fromisoformat(event["timestamp"]).strftime("%d %b %Y · %H:%M")
                    except (ValueError, TypeError, KeyError):
                        event_date = event.get("timestamp", "Date not recorded")
                    st.caption(f"{event_date}  ·  {event.get('audit_id') or 'Audit history'}")
                    st.markdown(f"**{event.get('item', 'Audit record')}**")
                    st.write(
                        f"{event.get('change', 'Updated')}: "
                        f"{event.get('previous_value', 'Not recorded')} → {event.get('new_value', 'Not recorded')}"
                    )
        else:
            st.caption("No audit activity has been recorded yet.")

    with st.expander("Previous audit memory", expanded=False):
        prior = st.session_state.prior_record
        st.caption(f"{prior['audit_id']}  ·  {prior['date']}  ·  {ORGANIZATION}")
        st.markdown(f"**{prior['control_id']}  ·  {prior['control_name']}**")
        show_status(prior["status"])
        st.write(prior["finding"])
        st.caption(f"Action owner: {prior['owner']}  ·  Due {prior['deadline']}  ·  {prior['action_status']}")
        if not st.session_state.prior_stored:
            if st.button("Store previous audit in Hindsight", type="primary"):
                try:
                    with st.spinner("Storing the prior finding and corrective action in Hindsight Cloud…"):
                        store_prior_audit(prior)
                    st.session_state.prior_stored = True
                    st.success("Prior finding and corrective action stored in Hindsight.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Hindsight could not store the audit record: {exc}")
        else:
            st.success("Prior audit record stored in Hindsight during this session.")

elif page == "Audit Data":
    render_audit_data()


elif page == "Evidence Verification":
    render_evidence_verification()


elif page == "Change History":
    render_change_history()


elif page == "Reminders":
    render_reminders()


elif page == "AI Assistant":
    render_ai_assistant()


elif page == "Audit Review":
    hero("Follow-up audit · AUD-2026-028", "Audit review", "Evidence is deterministic demo data. The assessment rules return a repeatable result; prior context comes from Hindsight Cloud.")
    st.caption(f"Organization: {ORGANIZATION} · Auditor: Taylor Morgan · Audit date: {date.today().isoformat()}")
    with st.container(horizontal=True):
        st.badge("Requirement", color="gray")
        st.badge("Evidence", color="blue")
        st.badge("AI assessment", color="orange")
        st.badge("Auditor decision", color="green")
    st.subheader("Controls and evidence")
    selected_controls = []
    for control in CONTROLS:
        with st.expander(f"{control['id']}  ·  {control['name']}  ·  {control['domain']}", expanded=control["id"] == "IR-02"):
            st.markdown("**Requirement**")
            st.write(control["requirement"])
            st.markdown("**Evidence provided**")
            st.write(control["evidence"])
            selected = st.checkbox("Include in this audit", value=True, key=f"include-{control['id']}")
            if selected:
                selected_controls.append(control)
    run_label = "Run follow-up audit with Hindsight recall" if st.session_state.prior_stored else "Run audit (store prior record first)"
    if st.button(run_label, type="primary", disabled=not st.session_state.prior_stored):
        try:
            with st.spinner("Recalling prior audit history from Hindsight Cloud…"):
                memories = recall_audit_history("incident response exercise open action status control IR-02")
                # Hindsight Cloud indexes retained memories asynchronously. Retry briefly so the demo can show a just-stored record.
                for _ in range(2):
                    if memories:
                        break
                    time.sleep(2)
                    memories = recall_audit_history("incident response exercise open action status control IR-02")
            history_text = "\n".join(memories).lower()
            findings = []
            for control in selected_controls:
                finding = {**control, "status": control["outcome"], "recurring": False, "historical_context": ""}
                is_prior_control = control["id"].lower() in history_text or control["name"].lower() in history_text
                if is_prior_control and control["outcome"] != "Compliant":
                    finding["recurring"] = True
                    finding["historical_context"] = next((m for m in memories if control["id"].lower() in m.lower() or control["name"].lower() in m.lower()), "")
                findings.append(finding)
            st.session_state.change_history.extend(
                finding_status_events(
                    st.session_state.audit_findings,
                    findings,
                    timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
                    source="Audit Review · Hindsight follow-up assessment",
                )
            )
            st.session_state.audit_findings = findings
            st.session_state.recalled_memories = memories
            if not memories:
                st.warning("The audit ran, but Hindsight returned no history yet. The UI will not label a finding recurring without recalled history. Confirm the prior record was stored, then rerun after indexing completes.")
            else:
                st.success(f"Follow-up audit complete. Hindsight recalled {len(memories)} memory record(s); matching prior controls are marked as recurring.")
        except Exception as exc:
            st.error(f"Hindsight recall failed, so this audit could not use prior history: {exc}")

    if st.session_state.audit_findings:
        st.divider()
        st.subheader("Assessment results", icon=":material/fact_check:")
        for finding in st.session_state.audit_findings:
            with st.container(border=True):
                title_cols = st.columns([2.5, 1, 1])
                title_cols[0].markdown(f"**{finding['id']} · {finding['name']}**")
                with title_cols[1]:
                    show_status(finding["status"])
                if finding["recurring"]:
                    title_cols[2].badge("Recurring finding", color="blue")
                st.caption(finding.get("requirement", "Requirement not recorded"))
                st.write(f"AI assessment · {finding['explanation']}")
                if finding["historical_context"]:
                    with st.expander("Previous audit · recalled from Hindsight"):
                        st.info(finding["historical_context"])


elif page == "Findings & Actions":
    hero("Remediation tracking", "Findings & corrective actions", "Assign an accountable owner, due date, and status, then save the action to Hindsight audit memory.")
    if not st.session_state.audit_findings:
        st.info("Run the follow-up audit first. Findings and their Hindsight context will appear here.")
    else:
        noncompliant = [f for f in st.session_state.audit_findings if f["status"] != "Compliant"]
        for finding in noncompliant:
            with st.container(border=True):
                cols = st.columns([2.4, 1, 1])
                cols[0].markdown(f"**{finding['id']} · {finding['name']}**")
                with cols[1]:
                    show_status(finding["status"])
                cols[2].badge("Recurring finding" if finding["recurring"] else "New finding", color="blue" if finding["recurring"] else "gray")
                st.caption(f"Owner: {finding.get('owner', 'Unassigned')} · Deadline: {finding.get('deadline') or 'Not set'} · Risk: {finding.get('risk') or 'Not recorded'}")
                st.write(finding.get("explanation", ""))
                if finding.get("evidence"):
                    st.caption(f"Evidence: {finding['evidence']}")
                if finding.get("action"):
                    st.caption(f"Corrective action: {finding['action']} · {finding.get('action_status') or 'Open'}")
                if finding["recurring"] and finding["historical_context"]:
                    with st.expander("Previous audit · recalled from Hindsight"):
                        st.info(finding["historical_context"])
        st.subheader("Create corrective action", icon=":material/task_alt:")
        with st.form("corrective-action-form"):
            eligible = noncompliant or st.session_state.audit_findings
            selected_id = st.selectbox("Finding", [f["id"] for f in eligible], format_func=lambda value: f"{value} · {next(f['name'] for f in eligible if f['id'] == value)}")
            selected_finding = next(f for f in eligible if f["id"] == selected_id)
            description = st.text_area("Corrective action", value=f"Address the evidence gap for {selected_finding['name']} and retain proof of completion.")
            c1, c2, c3 = st.columns(3)
            owner = c1.text_input("Owner", value=selected_finding["owner"])
            deadline = c2.date_input("Deadline", value=date.today().fromordinal(date.today().toordinal() + selected_finding["days"]))
            action_status = c3.selectbox("Status", ["Open", "In progress", "Blocked", "Closed"], index=1)
            submitted = st.form_submit_button("Save action to Hindsight", type="primary")
        if submitted:
            action = {"description": description, "owner": owner, "deadline": deadline.isoformat(), "status": action_status, "finding_id": selected_id}
            try:
                with st.spinner("Saving corrective action to Hindsight Cloud…"):
                    store_corrective_action(selected_finding, action)
                st.session_state.saved_actions.append(action)
                action_item = f"Corrective action for {selected_finding.get('control_id', selected_id)}"
                audit_id = selected_finding.get("audit_id", st.session_state.audit_id)
                record_history_change(
                    action_item, "Corrective action status", "Not created", action_status,
                    "Findings & Actions · action created", audit_id,
                )
                record_history_change(
                    action_item, "Owner", "Unassigned", owner,
                    "Findings & Actions · action created", audit_id,
                )
                record_history_change(
                    action_item, "Deadline", "Not set", action["deadline"],
                    "Findings & Actions · action created", audit_id,
                )
                st.success("Corrective action stored in Hindsight audit memory.")
            except Exception as exc:
                st.error(f"Hindsight could not store the corrective action: {exc}")
    if st.session_state.saved_actions:
        st.subheader("Actions created in this session")
        action_rows = [
            {
                "Finding": action["finding_id"],
                "Corrective action": action["description"],
                "Owner": action["owner"],
                "Deadline": action["deadline"],
                "Status": action["status"],
            }
            for action in st.session_state.saved_actions
        ]
        st.dataframe(pd.DataFrame(action_rows), hide_index=True, width="stretch")


elif page == "Memory Trail":
    hero(
        "Organization memory · Hindsight Cloud",
        "Audit memory trail",
        "Hindsight remembers previous audits, findings, actions, and evidence so follow-up audits can identify recurring issues.",
    )
    st.caption(f"Organization: {ORGANIZATION} · Memory bank: {BANK_ID}")
    prior = st.session_state.prior_record
    verifications = st.session_state.evidence_verifications
    latest_verification = verifications[-1] if verifications else None
    known_verification_memories = {
        verification_memory_content(event) for event in verifications
    }
    hindsight_records = [
        memory for memory in st.session_state.recalled_memories
        if memory not in known_verification_memories
    ]

    st.subheader("Audit history flow", icon=":material/account_tree:")
    st.caption("Previous audit  →  Finding  →  Corrective action")
    flow_top = st.columns(3, gap="small")
    with flow_top[0].container(border=True):
        st.caption("01 · PREVIOUS AUDIT")
        st.markdown(f"**{prior['audit_id']}**")
        st.write(f"{prior['date']} · {ORGANIZATION}")
        st.badge("Stored in Hindsight" if st.session_state.prior_stored else "Acme demo record", color="blue" if st.session_state.prior_stored else "gray")
    with flow_top[1].container(border=True):
        st.caption("02 · PREVIOUS FINDING")
        st.markdown(f"**{prior['control_id']} · {prior['control_name']}**")
        show_status(prior["status"])
        st.write(prior["finding"])
    with flow_top[2].container(border=True):
        st.caption("03 · CORRECTIVE ACTION")
        st.write(prior["action"])
        st.caption(f"Owner: {prior['owner']} · Due: {prior['deadline']}")
        show_status(prior["action_status"])

    st.caption("Evidence / resolution  →  Follow-up audit  →  Recalled memory")
    flow_bottom = st.columns(3, gap="small")
    with flow_bottom[0].container(border=True):
        st.caption("04 · EVIDENCE / RESOLUTION")
        if latest_verification:
            st.markdown(f"**{latest_verification['evidence_title'] or 'Evidence record'}**")
            st.caption(f"Evidence date: {latest_verification['evidence_date']} · Owner: {latest_verification['owner']}")
            st.write(f"AI assessment · {latest_verification['ai_assessment']} (recommendation)")
            st.write(f"Auditor decision · {latest_verification['auditor_decision']} (final)")
        else:
            st.caption("No evidence verification has been recorded in this session.")
    with flow_bottom[1].container(border=True):
        st.caption("05 · FOLLOW-UP AUDIT")
        if st.session_state.audit_findings:
            st.markdown(f"**{st.session_state.audit_id}**")
            st.write(f"{len(st.session_state.audit_findings)} control assessments recorded.")
            st.caption(f"Source: {st.session_state.audit_source}")
        else:
            st.caption("No follow-up assessment has been recorded in this session.")
    with flow_bottom[2].container(border=True):
        st.caption("06 · HINDSIGHT RECALL")
        st.metric("Recalled records", len(hindsight_records))
        if hindsight_records:
            st.badge("Historical memory", color="blue", icon=":material/database:")
        else:
            st.caption("No Hindsight recall results are available in this session yet.")

    if hindsight_records:
        with st.expander(f"View recalled Hindsight records ({len(hindsight_records)})", expanded=True):
            for index, memory in enumerate(hindsight_records, start=1):
                st.caption(f"Hindsight Cloud · recalled record {index}")
                with st.container(border=True):
                    st.write(memory)
    if verifications:
        with st.expander(f"Evidence verification records retained during this session ({len(verifications)})"):
            for event in reversed(verifications):
                st.caption(f"Retained after auditor decision · {event['verified_at']} · {event['control_id']}")
                with st.container(border=True):
                    st.write(verification_memory_content(event))
    if not hindsight_records and not verifications:
        st.info("No recall has run in this session yet. Store the prior audit from Dashboard, then run the follow-up audit.")
