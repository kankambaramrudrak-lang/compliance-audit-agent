# Hindsight Compliance Audit Prototype

A local Streamlit prototype for a company compliance audit. The first version uses fixed, deterministic audit evidence and assessment outcomes so the workflow is repeatable. It uses the existing Hindsight Cloud account to store prior findings and corrective actions, then recall that history during a follow-up audit. It does not use an LLM provider.

## Run locally

1. Activate the existing virtual environment:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. Install project dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Confirm the existing `.env` file contains `HINDSIGHT_API_KEY`. Keep that file private; it is excluded by `.gitignore`.

4. Start the app:

   ```powershell
   streamlit run app.py
   ```

## Demonstrate recurring findings

1. In **Dashboard**, store the seeded prior audit record in Hindsight. It contains a previous non-compliant incident response finding and its in-progress corrective action.
2. In **Audit Review**, run the follow-up audit. The app calls Hindsight recall before showing results.
3. The incident response control is marked **Recurring** only when the recalled history matches that control. The recalled memory appears with the finding and on **Memory Trail**.
4. In **Findings & Actions**, assign an owner, deadline, and status, then save the corrective action to Hindsight.

The demo uses the existing Hindsight Cloud endpoint (`https://api.hindsight.vectorize.io`) and memory bank (`compliance-audit`). Hindsight memory indexing can take a few seconds; the follow-up flow retries recall briefly after the initial store.

## Upload spreadsheet audit data

1. Open **Audit Data** and upload a CSV or Excel `.xlsx` file. Excel uploads use the first worksheet.
2. Review the preview, then select **Analyze audit data**. The app checks every row using deterministic rules and shows the result and explanation.
3. Detected findings appear in **Findings & Actions**, where you can assign an owner, deadline, and status. Findings and corrective actions use the existing Hindsight Cloud account, memory bank, organization tags, and metadata.

The analyzer recognizes common column names for control ID, control, requirement, evidence, status, owner, deadline, action, action status, and test status. It flags missing evidence, incomplete information, compliance gaps, overdue actions, untested controls, inconsistent status/evidence, and recurring findings when Hindsight recalls a matching prior control. With no upload, the page previews the existing Acme Technologies controls as demo data.

## Evidence verification

Open **Evidence Verification** after an audit has findings, select a finding, and enter an evidence title, description, date, and optional reference. The deterministic assessment reports **Supported**, **Insufficient**, or **Missing** as an observation only. The auditor then chooses the final decision; confirming it updates the finding and any related action and retains a verification record in Hindsight, with the AI assessment clearly separated from the auditor decision.

## Change history

Open **Change History** to review a chronological local log of audit finding/status changes, corrective-action status and assignment details, evidence updates, AI recommendations, and auditor decisions. The page starts with events seeded from the Acme Technologies prior audit and adds events as you use the audit workflow. The history is held in the current app session; important evidence decisions continue to be retained in Hindsight through the existing memory flow.

## Reminders and deadlines

Open **Reminders** to see corrective actions and uploaded audit deadlines with their owner, status, and urgency. Dates are classified locally as **Overdue**, **Due soon** (within 7 days), **Upcoming**, or **Completed**; the Acme prior-audit action provides an overdue example at startup. Update a deadline on the Reminders page to add the change to **Change History**. Overdue actions are also highlighted on the Dashboard. Reminders are in-app only; they do not send external notifications.

## AI Assistant

Open **AI Assistant** and ask about a control, prior finding, action, evidence, or decision. Each question first queries the existing Hindsight Cloud organization bank. Deterministic templates answer from recalled records and clearly labeled Acme/current-session fallback context; the supporting records are available under each answer. Derived observations, evidence assessments, and explicitly recorded final auditor decisions are shown separately. This prototype uses no additional LLM provider or API key.

## Project files

- `app.py` — Streamlit pages, deterministic review flow, corrective-action capture, and Hindsight retain/recall calls.
- `audit_data.py` — repeatable organization, control, evidence, and previous-audit fixtures.
- `spreadsheet_audit.py` — CSV/XLSX loading and deterministic spreadsheet assessment rules.
- `evidence_verification.py` — deterministic evidence assessment and verification memory formatting.
- `audit_history.py` — local change-history event and Acme demo-history helpers.
- `reminders.py` — deterministic due-date classification and reminder rows.
- `audit_assistant.py` — Hindsight/local context selection and deterministic, traceable answers.
- `requirements.txt` — Python dependencies.
