import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_data import prior_audit_record
from reminders import build_reminder_items, classify_deadline


class ReminderTests(unittest.TestCase):
    today = date(2026, 9, 28)

    def test_classifies_overdue_due_soon_upcoming_and_completed(self):
        self.assertEqual(classify_deadline(self.today - timedelta(days=1), "Open", today=self.today)["urgency"], "Overdue")
        self.assertEqual(classify_deadline(self.today + timedelta(days=7), "In progress", today=self.today)["urgency"], "Due soon")
        self.assertEqual(classify_deadline(self.today + timedelta(days=8), "Open", today=self.today)["urgency"], "Upcoming")
        self.assertEqual(classify_deadline(self.today - timedelta(days=30), "Closed", today=self.today)["urgency"], "Completed")

    def test_missing_or_unparseable_deadline_is_explicit(self):
        self.assertEqual(classify_deadline("", "Open", today=self.today)["urgency"], "No deadline")
        self.assertEqual(classify_deadline("someday", "Open", today=self.today)["urgency"], "No deadline")

    def test_acme_prior_action_seeds_an_overdue_reminder(self):
        prior = prior_audit_record(today=self.today)
        prior_action = {
            "control_id": prior["control_id"],
            "finding_name": prior["control_name"],
            "description": prior["action"],
            "owner": prior["owner"],
            "deadline": prior["deadline"],
            "status": prior["action_status"],
            "audit_id": prior["audit_id"],
        }
        items = build_reminder_items(
            saved_actions=[], prior_action=prior_action, findings=[], today=self.today
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["urgency"], "Overdue")
        self.assertEqual(items[0]["owner"], "Jordan Lee")
        self.assertEqual(items[0]["audit_id"], "AUD-2026-014")


if __name__ == "__main__":
    unittest.main()
