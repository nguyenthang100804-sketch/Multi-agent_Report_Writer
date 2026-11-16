import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
"""Refresh the OIL example from the current fact snapshot."""
import json
from pathlib import Path

from src.agents.state import snapshot_version_for_db, state_from_json, state_to_json
from src.schemas.report_schema import record_tool_result, research_limitation_text
from src.tools.agent_tools import AgentTools

path = Path("docs/examples/real-tool-report-state.json")
state = state_from_json(path.read_text(encoding="utf-8"))
task = state["outline"].sections[0].research_tasks[0]
with AgentTools() as tools:
    result = tools.execute("query_time_series_tool", {
        "ticker": state["request"].ticker, "scope": state["request"].scope,
        "item_code": task.item_code, "report_type": task.report_type,
        "start_year": task.start_year, "end_year": task.end_year})
    research, evidence = record_tool_result(
        task, result, snapshot_version_for_db(tools.db_path))
state["research_results"] = {task.task_id: research}
state["evidence_by_id"] = evidence
state["final_report"] = research_limitation_text(research, evidence)
path.write_text(json.dumps(json.loads(state_to_json(state)), ensure_ascii=False, indent=2),
                encoding="utf-8")
print(len(evidence), [record.payload.fact_index for record in evidence.values()])
