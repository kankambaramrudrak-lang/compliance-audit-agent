import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidence_verification import assess_evidence, verification_memory_content


class EvidenceVerificationTests(unittest.TestCase):
    requirement = "Review privileged access quarterly and document approvals"

    def test_missing_evidence_is_reported(self):
        result = assess_evidence(self.requirement, "", "", "2026-09-28")
        self.assertEqual(result["assessment"], "Missing")

    def test_incomplete_or_brief_evidence_is_insufficient(self):
        result = assess_evidence(self.requirement, "Access review", "Reviewed access", "2026-09-28")
        self.assertEqual(result["assessment"], "Insufficient")

    def test_relevant_dated_evidence_is_supported(self):
        result = assess_evidence(
            self.requirement,
            "Quarterly privileged access review",
            "Quarterly access review lists privileged accounts and documents manager approvals.",
            "2026-09-28",
            "Q3-review.xlsx",
        )
        self.assertEqual(result["assessment"], "Supported")
        self.assertIn("Auditor", result["explanation"])

    def test_memory_separates_ai_observation_and_auditor_decision(self):
        event = {
            "organization": "Acme Technologies",
            "audit_id": "AUD-TEST",
            "verified_at": "2026-09-28",
            "control_id": "IAM-04",
            "finding_name": "Privileged access review",
            "requirement": self.requirement,
            "evidence_title": "Q3 review",
            "evidence_description": "Review completed and approvals documented.",
            "evidence_date": "2026-09-27",
            "evidence_reference": "Q3.xlsx",
            "ai_assessment": "Supported",
            "ai_explanation": "Evidence relates to the requirement.",
            "auditor_decision": "Accept evidence",
            "final_status": "Resolved",
            "owner": "Jordan",
        }
        content = verification_memory_content(event)
        self.assertIn("AI assessment (observation/recommendation only): Supported", content)
        self.assertIn("Auditor decision (final): Accept evidence", content)
        self.assertIn("Owner: Jordan", content)


if __name__ == "__main__":
    unittest.main()
