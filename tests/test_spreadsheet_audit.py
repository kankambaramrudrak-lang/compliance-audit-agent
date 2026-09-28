import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_data import CONTROLS, ORGANIZATION
from spreadsheet_audit import (
    analyze_audit_dataframe,
    dataframe_from_controls,
    load_audit_file,
)


class SpreadsheetAuditTests(unittest.TestCase):
    def analyze_one(self, row, memories=None):
        reviews, findings = analyze_audit_dataframe(
            pd.DataFrame([row]),
            ORGANIZATION,
            "AUD-TEST",
            prior_memories=memories,
            today=date(2026, 9, 28),
        )
        return reviews[0], findings

    def test_loads_csv(self):
        frame = load_audit_file("audit.csv", b"Control,Status\nAccess review,Pass\n")
        self.assertEqual(frame.iloc[0]["Control"], "Access review")

    def test_loads_first_xlsx_sheet(self):
        workbook = BytesIO()
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            pd.DataFrame({"Control": ["Access review"], "Status": ["Pass"]}).to_excel(
                writer, sheet_name="Controls", index=False
            )
        frame = load_audit_file("audit.xlsx", workbook.getvalue())
        self.assertEqual(frame.iloc[0]["Control"], "Access review")

    def test_missing_evidence_and_failed_status_create_a_finding(self):
        review, findings = self.analyze_one(
            {
                "Control ID": "IAM-04",
                "Control": "Privileged access",
                "Requirement": "Review privileged access quarterly",
                "Evidence": "",
                "Status": "Non-compliant",
                "Test status": "Tested",
            }
        )
        self.assertEqual(review["status"], "Non-compliant")
        self.assertIn("Missing evidence", review["exceptions"])
        self.assertIn("Compliance gap", review["exceptions"])
        self.assertEqual(len(findings), 1)
        self.assertIn("control_id", findings[0])

    def test_detects_overdue_actions_untested_controls_and_inconsistent_data(self):
        review, _ = self.analyze_one(
            {
                "Control ID": "IR-02",
                "Control": "Incident response",
                "Requirement": "Track response actions to completion",
                "Evidence": "A weak process is fully implemented",
                "Status": "Compliant",
                "Action": "Assign action owners",
                "Owner": "Jordan",
                "Deadline": "2026-09-01",
                "Action Status": "In progress",
                "Test Status": "Not tested",
            }
        )
        self.assertIn("Overdue action", review["exceptions"])
        self.assertIn("Untested control", review["exceptions"])
        self.assertIn("Inconsistent information", review["exceptions"])

    def test_hindsight_match_marks_same_control_recurring(self):
        review, _ = self.analyze_one(
            {
                "Control ID": "IR-02",
                "Control": "Incident response exercises",
                "Requirement": "Exercise the incident response plan annually",
                "Evidence": "Two actions remain open",
                "Status": "Non-compliant",
                "Test status": "Tested",
            },
            memories=[
                "Organization: Acme Technologies (acme-technologies). Previous compliance audit. "
                "Control IR-02: Incident response exercises. Finding: actions remain open."
            ],
        )
        self.assertTrue(review["recurring"])
        self.assertIn("Recurring finding", review["exceptions"])

    def test_uploaded_audit_export_schema_maps_all_five_status_values(self):
        export = pd.DataFrame([
            {
                "control_id": "IAM-01",
                "requirement": "Review access quarterly",
                "evidence": "The access review was approved on 2020-01-10 and records were retained.",
                "status": "Compliant",
                "finding": "No issue identified",
                "owner": "Alex",
                "risk": "Low",
                "deadline": "",
                "notes": "Reviewed",
            },
            {
                "control_id": "IR-02",
                "requirement": "Exercise the incident response plan annually",
                "evidence": "The annual exercise was not completed.",
                "status": "Gap",
                "finding": "Annual exercise not completed",
                "owner": "Jordan",
                "risk": "High",
                "deadline": "",
                "notes": "Follow up",
            },
            {
                "control_id": "TPRM-01",
                "requirement": "Review current vendor assurance",
                "evidence": "A vendor register was supplied.",
                "status": "Needs Review",
                "finding": "Review sign-off is not attached",
                "owner": "Sam",
                "risk": "Medium",
                "deadline": "",
                "notes": "",
            },
            {
                "control_id": "BCP-01",
                "requirement": "Test recovery procedures annually",
                "evidence": "No recovery test record was located.",
                "status": "Untested",
                "finding": "No test evidence",
                "owner": "Lee",
                "risk": "Medium",
                "deadline": "",
                "notes": "",
            },
            {
                "control_id": "IR-03",
                "requirement": "Track incident response actions to closure",
                "evidence": "Prior finding is still referenced.",
                "status": "Recurring",
                "finding": "Repeated from an earlier audit",
                "owner": "Jordan",
                "risk": "High",
                "deadline": "",
                "notes": "",
            },
        ])
        reviews, findings = analyze_audit_dataframe(
            export, ORGANIZATION, "AUD-EXPORT", today=date(2026, 9, 28)
        )
        by_control = {review["control_id"]: review for review in reviews}

        self.assertEqual(by_control["IAM-01"]["status"], "Compliant")
        self.assertNotIn("Untested control", by_control["IAM-01"]["exceptions"])
        self.assertNotIn("Overdue action", by_control["IAM-01"]["exceptions"])
        self.assertEqual(by_control["IR-02"]["status"], "Non-compliant")
        self.assertIn("Compliance gap", by_control["IR-02"]["exceptions"])
        self.assertEqual(by_control["TPRM-01"]["status"], "Insufficient Evidence")
        self.assertIn("Review required", by_control["TPRM-01"]["exceptions"])
        self.assertEqual(by_control["BCP-01"]["status"], "Insufficient Evidence")
        self.assertIn("Untested control", by_control["BCP-01"]["exceptions"])
        self.assertTrue(by_control["IR-03"]["recurring"])
        self.assertIn("Recurring finding", by_control["IR-03"]["exceptions"])
        self.assertEqual(by_control["IAM-01"]["finding"], "No issue identified")
        self.assertEqual(by_control["IAM-01"]["risk"], "Low")
        self.assertNotIn("IAM-01", [item["control_id"] for item in findings])

    def test_export_deadline_is_not_a_corrective_action_deadline_without_action(self):
        review, _ = self.analyze_one({
            "control_id": "IAM-08",
            "requirement": "Review access quarterly",
            "evidence": "The review was approved on 2020-01-10.",
            "status": "Compliant",
            "finding": "No gap",
            "owner": "Taylor",
            "risk": "Low",
            "deadline": "2020-01-01",
            "notes": "No corrective action expected",
        })
        self.assertEqual(review["status"], "Compliant")
        self.assertNotIn("Overdue action", review["exceptions"])
        self.assertNotIn("Incomplete information", review["exceptions"])
        self.assertEqual(review["deadline"], "")

    def test_overdue_is_only_checked_for_a_real_action_with_a_valid_deadline(self):
        review, _ = self.analyze_one({
            "control_id": "IR-02",
            "requirement": "Track response actions",
            "evidence": "A tabletop exercise was held.",
            "status": "Needs Review",
            "finding": "Two actions remain open",
            "owner": "Jordan",
            "risk": "High",
            "deadline": "2026-09-01",
            "action": "Close the two exercise follow-ups",
            "action_status": "In progress",
        })
        self.assertIn("Overdue action", review["exceptions"])
        self.assertEqual(review["deadline"], "2026-09-01")

    def test_ir02_export_row_is_recurring_when_hindsight_memory_is_recalled(self):
        review, _ = self.analyze_one({
            "control_id": "IR-02",
            "requirement": "Exercise the incident response plan annually",
            "evidence": "The exercise record is attached.",
            "status": "Compliant",
            "finding": "Actions were tracked",
            "owner": "Jordan",
            "risk": "Medium",
            "deadline": "",
            "notes": "",
        }, memories=[
            "Organization: Acme Technologies. Previous compliance audit AUD-2026-014. "
            "Control IR-02: Incident response exercises. Finding: actions remained open."
        ])
        self.assertTrue(review["recurring"])
        self.assertIn("Recurring finding", review["exceptions"])
        self.assertIn("IR-02", review["historical_context"])

    def test_related_memories_without_a_prior_issue_do_not_mark_controls_recurring(self):
        benign_memories = [
            "Organization: Acme Technologies. Control IAM-04: Privileged access. "
            "Quarterly access review completed and evidence retained. Finding status: Compliant.",
            "Organization: Acme Technologies. Control CRYPTO-03: Encryption. "
            "Key rotation evidence reviewed. Control status: Compliant.",
            "Organization: Acme Technologies. Control LOG-06: Audit logging. "
            "Logging configuration was documented. No findings and no open actions.",
        ]
        current_controls = [
            ("IAM-04", "Privileged access", "Review privileged access quarterly"),
            ("CRYPTO-03", "Encryption", "Rotate encryption keys annually"),
            ("LOG-06", "Audit logging", "Retain security logs"),
        ]

        for (control_id, name, requirement), memory in zip(current_controls, benign_memories):
            with self.subTest(control_id=control_id):
                review, _ = self.analyze_one({
                    "control_id": control_id,
                    "control": name,
                    "requirement": requirement,
                    "evidence": "Current evidence was reviewed.",
                    "status": "Compliant",
                }, memories=[memory])
                self.assertFalse(review["recurring"])
                self.assertNotIn("Recurring finding", review["exceptions"])
                self.assertEqual(review["historical_context"], "")

    def test_compliant_historical_record_with_closed_action_is_not_recurring(self):
        review, _ = self.analyze_one({
            "control_id": "IAM-04",
            "control": "Privileged access",
            "requirement": "Review privileged access quarterly",
            "evidence": "Current access review approved.",
            "status": "Compliant",
        }, memories=[
            "Organization: Acme Technologies. Control IAM-04: Privileged access. "
            "Finding status: Compliant. Corrective action status: Closed. No issues found."
        ])
        self.assertFalse(review["recurring"])
        self.assertNotIn("Recurring finding", review["exceptions"])

    def test_negated_historical_issue_language_does_not_mark_control_recurring(self):
        review, _ = self.analyze_one({
            "control_id": "CRYPTO-03",
            "control": "Encryption",
            "requirement": "Rotate encryption keys annually",
            "evidence": "Rotation records are complete.",
            "status": "Compliant",
        }, memories=[
            "Organization: Acme Technologies. Control CRYPTO-03: Encryption. "
            "No known gaps, no prior findings, and no unresolved actions."
        ])
        self.assertFalse(review["recurring"])

    def test_explicit_prior_finding_marks_compliant_control_as_recurring(self):
        review, _ = self.analyze_one({
            "control_id": "IAM-04",
            "control": "Privileged access",
            "requirement": "Review privileged access quarterly",
            "evidence": "Current review approved.",
            "status": "Compliant",
        }, memories=[
            "Organization: Acme Technologies. Control IAM-04: Privileged access. "
            "Previous finding status: Non-compliant; corrective action status: In progress."
        ])
        self.assertTrue(review["recurring"])
        self.assertIn("Recurring finding", review["exceptions"])

    def test_issue_for_another_control_in_same_memory_does_not_carry_over(self):
        memory = (
            "Organization: Acme Technologies. Previous audit. "
            "Control IR-02: Finding: prior finding; open corrective actions remain. "
            "Control LOG-06: Logging configuration documented and compliant."
        )
        review, _ = self.analyze_one({
            "control_id": "LOG-06",
            "control": "Audit logging",
            "requirement": "Retain security logs",
            "evidence": "Current logging configuration reviewed.",
            "status": "Compliant",
        }, memories=[memory])
        self.assertFalse(review["recurring"])
        self.assertNotIn("Recurring finding", review["exceptions"])

    def test_current_row_finding_text_alone_does_not_make_it_recurring(self):
        review, _ = self.analyze_one({
            "control_id": "TPRM-07",
            "control": "Vendor assurance",
            "requirement": "Review vendor assurance annually",
            "evidence": "Current assurance report reviewed.",
            "status": "Compliant",
            "finding": "Previous finding: vendor evidence was missing and remediation overdue.",
        }, memories=[
            "Organization: Acme Technologies. Control TPRM-07: Vendor assurance reviewed. "
            "Current report recorded as compliant."
        ])
        self.assertFalse(review["recurring"])
        self.assertNotIn("Recurring finding", review["exceptions"])

    def test_recalled_memory_requires_explicit_issue_language(self):
        for memory in (
            "Organization: Acme Technologies. Control BCP-09: Recovery plan audit reviewed.",
            "Organization: Acme Technologies. Control SEC-11: Prior audit records were retained.",
            "Organization: Acme Technologies. Control IAM-04: Finding reviewed and closed.",
        ):
            with self.subTest(memory=memory):
                control_id = memory.split("Control ", 1)[1].split(":", 1)[0]
                review, _ = self.analyze_one({
                    "control_id": control_id,
                    "requirement": "Review the control annually",
                    "evidence": "Current evidence is complete.",
                    "status": "Compliant",
                }, memories=[memory])
                self.assertFalse(review["recurring"])

    def test_existing_acme_controls_remain_a_fallback_dataset(self):
        frame = dataframe_from_controls(CONTROLS)
        self.assertEqual(len(frame), len(CONTROLS))
        self.assertIn("Requirement", frame.columns)
        self.assertIn("Evidence", frame.columns)
        reviews, findings = analyze_audit_dataframe(frame, ORGANIZATION, "AUD-FALLBACK")
        self.assertEqual(len(reviews), len(CONTROLS))
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main()
