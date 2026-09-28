import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_data import prior_audit_record
from audit_history import finding_status_events, seed_demo_history


class AuditHistoryTests(unittest.TestCase):
    def test_demo_history_is_seeded_from_prior_audit(self):
        history = seed_demo_history(prior_audit_record())
        self.assertGreaterEqual(len(history), 4)
        self.assertTrue(any(event["change"] == "Owner" for event in history))
        self.assertTrue(any(event["change"] == "Deadline" for event in history))
        self.assertTrue(any(event["audit_id"] == "AUD-2026-014" for event in history))

    def test_finding_status_transition_records_previous_and_new_values(self):
        previous = [{"control_id": "IR-02", "name": "Incident response", "status": "Non-compliant"}]
        current = [{
            "control_id": "IR-02", "name": "Incident response", "status": "Resolved", "audit_id": "AUD-NEW"
        }]
        events = finding_status_events(
            previous,
            current,
            timestamp="2026-09-28T12:00:00+05:30",
            source="Evidence Verification",
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["previous_value"], "Non-compliant")
        self.assertEqual(events[0]["new_value"], "Resolved")
        self.assertEqual(events[0]["audit_id"], "AUD-NEW")

    def test_unchanged_finding_status_does_not_create_noise(self):
        finding = {"control_id": "IAM-04", "status": "Compliant"}
        self.assertEqual(
            finding_status_events([finding], [finding], timestamp="2026-09-28T12:00:00", source="test"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
