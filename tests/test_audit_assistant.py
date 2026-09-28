import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_assistant import answer_audit_question, demo_context_records
from audit_data import CONTROLS, prior_audit_record


class AuditAssistantTests(unittest.TestCase):
    def setUp(self):
        self.local = demo_context_records(prior_audit_record(), CONTROLS)

    def test_demo_fallback_answers_owner_without_calling_it_recalled(self):
        result = answer_audit_question("Who was responsible for the IR-02 action?", [], self.local)
        self.assertTrue(any(value == "Jordan Lee" for value, _ in result["facts"]))
        self.assertTrue(all("local" in source.lower() for _, source in result["facts"]))
        self.assertEqual(result["recalled"], [])

    def test_previous_audit_question_does_not_mislabel_demo_baseline_as_history(self):
        result = answer_audit_question("What evidence was provided for IR-02 in the previous audit?", [], self.local)
        self.assertIn("do not contain an explicit evidence detail", result["answer"])
        self.assertTrue(all("prior-audit" in record["source"] for record in result["local_records"]))

    def test_ai_assessment_and_auditor_decision_are_kept_distinct(self):
        memory = (
            "Audit AUD-2026-028. Control IR-02: Incident response. "
            "AI assessment (observation/recommendation only): Insufficient. "
            "AI explanation: The evidence is brief. Auditor decision (final): Request more evidence. "
            "Resulting finding status: Under Review."
        )
        result = answer_audit_question("What did the auditor decide for IR-02?", [memory], [])
        self.assertEqual(result["auditor_decisions"][0][0], "Request more evidence")
        self.assertEqual(result["ai_assessments"][0][0], "Insufficient")
        self.assertIn("Hindsight Cloud recall", result["auditor_decisions"][0][1])

    def test_absent_auditor_decision_is_not_inferred_from_ai_assessment(self):
        memory = "Control IR-02. AI assessment (observation/recommendation only): Supported."
        result = answer_audit_question("What did the auditor decide for IR-02?", [memory], [])
        self.assertEqual(result["auditor_decisions"], [])
        self.assertIn("No explicit auditor decision", result["answer"])

    def test_change_history_and_recurring_observation_are_labeled_as_derived(self):
        records = [
            {"source": "Hindsight Cloud recall", "text": "Audit AUD-2026-014. Control IR-02. Finding status: Non-compliant."},
            {"source": "Current audit session finding (AUD-2026-028)", "text": "Audit AUD-2026-028. Control IR-02. Finding status: Insufficient Evidence."},
        ]
        result = answer_audit_question("Has IR-02 appeared as a recurring finding?", [], records)
        self.assertIn("2 distinct audit records", result["observation"])
        self.assertIn("not an auditor decision", result["observation"])


if __name__ == "__main__":
    unittest.main()
