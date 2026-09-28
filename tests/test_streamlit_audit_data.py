import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class AuditDataPageTests(unittest.TestCase):
    def open_page(self, app, page):
        app.button(key=f"nav-{page}").click().run(timeout=20)

    def test_audit_data_page_renders_in_existing_app_navigation(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        self.open_page(app, "Audit Data")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Audit Data")
        self.assertEqual(app.file_uploader[0].label, "Upload audit data")
        self.assertTrue(any("Acme Technologies" in item.value for item in app.info))

    def test_evidence_verification_page_is_in_workspace_navigation(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        app.session_state["audit_findings"] = [{
            "id": "IAM-04-ROW-0002",
            "control_id": "IAM-04",
            "name": "Privileged access review",
            "requirement": "Review privileged access quarterly and document approvals",
            "status": "Insufficient Evidence",
            "outcome": "Insufficient Evidence",
            "owner": "Jordan",
            "audit_id": "AUD-TEST",
            "explanation": "Test finding",
            "recurring": False,
            "historical_context": "",
            "days": 14,
        }]
        self.open_page(app, "Evidence Verification")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Verify evidence against a finding")
        self.assertTrue(any(item.label == "Evidence title/name" for item in app.text_input))
        self.assertTrue(any(item.label == "Evidence description" for item in app.text_area))
        self.assertTrue(any(item.label == "Evidence date" for item in app.date_input))

    def test_change_history_page_starts_with_demo_events(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        self.open_page(app, "Change History")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Change History")
        self.assertTrue(any("seeded Acme Technologies prior audit history" in item.value for item in app.caption))
        self.assertGreater(len(app.dataframe), 0)

    def test_reminders_page_shows_seeded_acme_action(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        self.open_page(app, "Reminders")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Reminders")
        self.assertGreater(len(app.dataframe), 0)
        self.assertEqual(app.dataframe[0].value.iloc[0]["Urgency"], "Overdue")

    def test_dashboard_command_center_loads_with_attention_deadlines_and_activity(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)

        self.assertFalse(app.exception)
        metric_labels = {item.label for item in app.metric}
        self.assertIn("Controls in scope", metric_labels)
        self.assertIn("Compliant", metric_labels)
        self.assertIn("Open findings", metric_labels)
        self.assertIn("Evidence gaps", metric_labels)
        self.assertIn("Recurring findings", metric_labels)
        self.assertIn("Overdue actions", metric_labels)
        overdue_metric = next(item for item in app.metric if item.label == "Overdue actions")
        self.assertEqual(overdue_metric.value, "1")
        section_titles = {item.value for item in app.subheader}
        self.assertIn("Needs attention", section_titles)
        self.assertIn("Compliance & risk", section_titles)
        self.assertIn("Upcoming deadlines", section_titles)
        self.assertIn("Recent audit activity", section_titles)

    def test_ai_assistant_page_renders_without_an_external_llm(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        self.open_page(app, "AI Assistant")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "AI Assistant")
        self.assertTrue(any("not an LLM" in item.value for item in app.caption))
        self.assertEqual(len(app.chat_input), 1)

    def test_memory_trail_explains_the_audit_history_flow(self):
        app_file = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_file)).run(timeout=20)
        self.open_page(app, "Memory Trail")

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Audit memory trail")
        self.assertTrue(any("01 · PREVIOUS AUDIT" in item.value for item in app.caption))
        self.assertTrue(any("06 · HINDSIGHT RECALL" in item.value for item in app.caption))


if __name__ == "__main__":
    unittest.main()
