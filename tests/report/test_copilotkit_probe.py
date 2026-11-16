"""The approval probe must survive a server restart without losing its revision."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from scripts.prototypes.copilotkit_backend import create_app
from src.schemas.report_schema import PlannerNote, PlannerOutput, ReportOutline, SectionPlan


def sample_plan(_request):
    return ReportOutline(outline_id="prototype-HUT", sections=[SectionPlan(
        section_id="S1", title="Tổng quan HUT", objective="Mục tiêu mẫu")])


class CopilotKitProbeTests(unittest.TestCase):
    def test_revise_restart_approve(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "checkpoints.sqlite"
            with TestClient(create_app(database, sample_plan, lambda _state: {}, Mock())) as client:
                started = client.post("/runs/probe", json={
                    "ticker": "HUT", "start_year": 2022, "end_year": 2025,
                    "audience": "demo",
                })
                self.assertEqual(started.status_code, 200)
                self.assertTrue(started.json()["pending_interrupt"])
                outline = started.json()["outline"]
                outline["sections"][0]["objective"] = "Đã chỉnh"
                revised = client.post("/runs/probe/resume", json={
                    "action": "revise", "outline_version": 1, "outline": outline,
                })
                self.assertEqual(revised.status_code, 200)
                self.assertEqual(revised.json()["outline_version"], 2)

            with TestClient(create_app(database, sample_plan, lambda _state: {}, Mock())) as client:
                pending = client.get("/runs/probe").json()
                self.assertTrue(pending["pending_interrupt"])
                self.assertEqual(pending["outline"]["sections"][0]["objective"], "Đã chỉnh")
                stale = client.post("/runs/probe/resume", json={
                    "action": "approve", "outline_version": 1,
                })
                self.assertEqual(stale.status_code, 409)
                approved = client.post("/runs/probe/resume", json={
                    "action": "approve", "outline_version": 2,
                })
                self.assertEqual(approved.status_code, 200)
                self.assertEqual(approved.json()["outline_approved_version"], 2)
                self.assertEqual(approved.json()["run_status"], "incomplete")

    def test_planner_clarification_is_visible(self):
        def plan(_request):
            return PlannerOutput(status="needs_clarification",
                                 available_scopes={"separate": [2023, 2024]},
                                 notes=[PlannerNote(code="scope_or_year_missing",
                                                    message="Thiếu dữ liệu năm 2022")])

        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "checkpoints.sqlite", plan,
                                       lambda _state: {}, Mock())) as client:
                response = client.post("/runs/clarify", json={
                    "ticker": "HUT", "start_year": 2022, "end_year": 2024,
                    "audience": "demo",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["run_status"], "needs_clarification")
                self.assertEqual(response.json()["available_scopes"], {"separate": [2023, 2024]})
                self.assertEqual(response.json()["planner_notes"][0]["code"], "scope_or_year_missing")

    def test_agui_uses_planner_result(self):
        def plan(_request):
            return PlannerOutput(status="ready", outline=sample_plan(_request),
                                 notes=[PlannerNote(code="review", message="Kiểm tra dàn ý")])

        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "checkpoints.sqlite", plan,
                                       lambda _state: {}, Mock())) as client:
                response = client.post("/agent", json={
                    "threadId": "agui", "runId": "run-1", "messages": [], "tools": [],
                    "context": [], "forwardedProps": {},
                    "state": {"request": {"ticker": "HUT", "start_year": 2022,
                                          "end_year": 2025, "audience": "demo"}},
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn('"name":"on_interrupt"', response.text)
                snapshot = client.get("/runs/agui").json()
                self.assertEqual(snapshot["run_status"], "awaiting_approval")
                self.assertEqual(snapshot["planner_notes"][0]["code"], "review")


if __name__ == "__main__":
    unittest.main()
