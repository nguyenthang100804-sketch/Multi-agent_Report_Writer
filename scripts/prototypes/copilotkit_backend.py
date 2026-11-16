"""AG-UI adapter for Planner review, Researcher, and Writer drafts."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Literal

import truststore

# The application uses Windows' trusted roots for Gemini's HTTPS connection.
truststore.inject_into_ssl()

import aiosqlite
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from google.genai import types
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.config import get_config
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.agents.llm_writer import build_llm_writer
from src.agents.planner_agent import build_planner_agent
from src.agents.planner_model import GeminiPlannerModel, _gemini_client, _read_api_key
from src.agents.researcher import build_researcher
from src.agents.report_graph import build_report_graph
from src.agents.report_tables import render_section_tables
from src.agents.state import ReportState, is_run_complete, report_checkpoint_serde
from src.agents.verifier_contract import VerifierModel
from src.agents.verifier_model import GeminiVerifierModel
from src.agents.writer_model import GeminiWriterModel
from src.schemas.report_schema import PlannerOutput, ReportOutline, ReportRequest
from src.tools.agent_tools import AgentTools


DEFAULT_CHECKPOINT = Path(__file__).resolve().parents[2] / "ui-prototype" / ".data" / "checkpoints.sqlite"
LOGGER = logging.getLogger(__name__)


def _json_safe_keys(value):
    """Keep tuple-keyed graph state JSON-safe when AG-UI emits raw events."""
    if isinstance(value, dict):
        return {(str(key) if isinstance(key, tuple) else key): _json_safe_keys(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_keys(item) for item in value]
    return value


class ReportAGUIAgent(LangGraphAGUIAgent):
    def _dispatch_event(self, event):
        if isinstance(getattr(event, "event", None), dict):
            event.event = _json_safe_keys(event.event)
        if isinstance(getattr(event, "raw_event", None), dict):
            event.raw_event = _json_safe_keys(event.raw_event)
        return super()._dispatch_event(event)


class ResumeInput(BaseModel):
    action: str
    outline_version: int
    outline: dict | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


def create_app(checkpoint_path: Path = DEFAULT_CHECKPOINT,
               planner: Callable[[ReportRequest], PlannerOutput | ReportOutline] | None = None,
               writer: Callable[[ReportState], dict] | None = None,
               verifier_model: VerifierModel | None = None) -> FastAPI:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    progress_lock = Lock()
    progress_events: dict[str, list[dict]] = {}

    def emit_progress(stage: str, message: str) -> None:
        try:
            thread_id = get_config()["configurable"]["thread_id"]
        except (RuntimeError, KeyError):
            LOGGER.warning("Progress event has no graph config", exc_info=True)
            return
        with progress_lock:
            events = progress_events.setdefault(thread_id, [])
            events.append({"id": len(events) + 1,
                           "stage": stage, "message": message})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with aiosqlite.connect(str(checkpoint_path)) as connection:
            with AgentTools() as tools:
                if planner is None:
                    plan = build_planner_agent(
                        GeminiPlannerModel(), tools, progress=emit_progress,
                    )
                else:
                    plan = planner
                research = build_researcher(tools, progress=emit_progress)
                write = writer if writer is not None else build_llm_writer(
                    GeminiWriterModel(), progress=emit_progress)
                verifier = verifier_model if verifier_model is not None else GeminiVerifierModel()

                def research_node(state):
                    request = ReportRequest.model_validate(state["request"])
                    task_count = sum(len(section.research_tasks)
                                     for section in state["outline"].sections)
                    emit_progress("research", f"Researcher bắt đầu xử lý {task_count} tác vụ trong dàn ý")
                    update = research({**state, "request": request})
                    emit_progress("research_done", f"Researcher đã tra cứu {len(update.get('research_results', {}))} mục"
                                  f" · {len(update.get('evidence_by_id', {}))} bằng chứng"
                                  f" · {len(update.get('calculations_by_id', {}))} phép tính")
                    return {**update,
                            "request": request, "research_completed": True}

                def writer_node(state):
                    emit_progress("writer", f"Writer bắt đầu tạo {len(state['outline'].sections)} phần bản nháp")
                    update = write(state)
                    emit_progress("writer_done", f"Writer đã tạo {len(update.get('section_drafts', {}))} phần bản nháp")
                    return {**update, "writer_completed": True}

                saver = AsyncSqliteSaver(connection, serde=report_checkpoint_serde())
                graph = build_report_graph(
                    lambda raw: plan(ReportRequest.model_validate(raw)),
                    research_node,
                    writer_node,
                    verifier_model=verifier, verifier_mode="blocking",
                    require_outline_approval=True, checkpointer=saver,
                    progress=emit_progress,
                )
                app.state.graph = graph
                app.state.chat_client = None
                add_langgraph_fastapi_endpoint(
                    app, ReportAGUIAgent(name="report_probe", graph=graph), path="/agent",
                )
                yield

    app = FastAPI(lifespan=lifespan)

    @app.post("/runs/{thread_id}/progress")
    async def reset_progress(thread_id: str):
        with progress_lock:
            progress_events[thread_id] = []
        return {"ok": True}

    @app.get("/runs/{thread_id}/progress")
    async def stream_progress(thread_id: str, request: Request):
        async def events():
            next_index = 0
            yield ": connected\n\n"
            ticks = 0
            while not await request.is_disconnected():
                with progress_lock:
                    pending = progress_events.get(thread_id, [])[next_index:]
                    next_index += len(pending)
                for item in pending:
                    yield f"id: {item['id']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.25)
                ticks += 1
                if ticks >= 60:
                    yield ": keepalive\n\n"
                    ticks = 0

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/runs/{thread_id}")
    async def start_run(thread_id: str, request: ReportRequest):
        graph = app.state.graph
        config = {"configurable": {"thread_id": thread_id}}
        if (await graph.aget_state(config)).values:
            raise HTTPException(409, "Thread already exists")
        await graph.ainvoke({"request": request}, config)
        return await get_run(thread_id)

    @app.get("/runs/{thread_id}")
    async def get_run(thread_id: str):
        graph = app.state.graph
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        if not snapshot.values:
            raise HTTPException(404, "Thread not found")
        state = snapshot.values
        writer_sections = []
        for section in state["outline"].sections if state.get("outline") else []:
            drafts = [draft for draft in state.get("section_drafts", {}).values()
                      if draft.section_id == section.section_id and
                      draft.outline_version == state.get("outline_version")]
            draft = max(drafts, key=lambda item: item.revision) if drafts else None
            log = (state.get("writer_run_logs", {}).get(
                f"{draft.outline_version}:{draft.section_id}:{draft.revision}")
                if draft else None)
            verifier_log = (state.get("verifier_run_logs", {}).get(
                f"{draft.outline_version}:{draft.section_id}:{draft.revision}")
                if draft else None)
            checks = [item for item in state.get("verification_results", {}).values()
                      if draft and item.section_id == draft.section_id and
                      item.revision == draft.revision and
                      item.outline_version == draft.outline_version]
            check = checks[-1] if checks else None
            writer_sections.append({
                "section_id": section.section_id, "title": section.title,
                "draft_revision": draft.revision if draft else None,
                "text": "\n\n".join(block.text for block in draft.blocks) if draft else None,
                "table_markdown": (render_section_tables(section, state)
                                   if check and check.status == "passed" and
                                   state.get("run_status") in ("incomplete", "completed") else ""),
                "used_fallback": log.used_fallback if log else None,
                "attempts": log.attempts if log else None,
                "writer_errors": ([error for attempt in log.errors_by_attempt
                                   for error in attempt] if log and log.used_fallback else []),
                "verification_status": check.status if check else None,
                "verification_level": check.level if check else None,
                "verification_issues": [
                    {"error_type": issue.error_type, "reason": issue.reason,
                     "severity": issue.severity, "action": issue.action}
                    for issue in check.issues] if check else [],
                "semantic_called": verifier_log.semantic_called if verifier_log else False,
                "semantic_status": verifier_log.semantic_status if verifier_log else None,
                "verifier_error": verifier_log.error_message if verifier_log else None,
            })
        return {
            "request": ReportRequest.model_validate(state["request"]).model_dump(mode="json"),
            "outline": state["outline"].model_dump(mode="json") if state.get("outline") else None,
            "outline_version": state.get("outline_version"),
            "outline_approved_version": state.get("outline_approved_version"),
            "run_status": state.get("run_status"),
            "planner_notes": [note.model_dump(mode="json") for note in state.get("planner_notes", [])],
            "available_scopes": state.get("planner_available_scopes", {}),
            "outline_decisions": [item.model_dump(mode="json")
                                  for item in state.get("outline_decisions", [])],
            "planner_observations": [
                {"observation_id": key, "tool_name": item.tool_name,
                 "status": item.result.status, "missing_years": item.result.missing_years,
                 "warnings": item.result.warnings,
                 "safe_for_calculation": item.result.safe_for_calculation}
                for key, item in state.get("planner_observations", {}).items()
            ],
            "planner_used_fallback": state.get("planner_used_fallback", False),
            "research_completed": state.get("research_completed", False),
            "research_results": [
                {"task_id": task_id, "status": result.status,
                 "evidence_count": len(result.evidence_ids),
                 "missing": [item.model_dump(mode="json") for item in result.missing],
                 "warnings": result.warnings, "issues": result.issues,
                 "next_action": result.next_action}
                for task_id, result in state.get("research_results", {}).items()
            ],
            "evidence_count": len(state.get("evidence_by_id", {})),
            "calculation_count": len(state.get("calculations_by_id", {})),
            "writer_completed": state.get("writer_completed", False),
            "writer_sections": writer_sections,
            "final_report": state.get("final_report") if is_run_complete(state) else None,
            "pending_interrupt": bool(snapshot.tasks and snapshot.tasks[0].interrupts),
        }

    async def completed_report(thread_id: str):
        snapshot = await app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
        if not snapshot.values:
            raise HTTPException(404, "Thread not found")
        state = snapshot.values
        if not is_run_complete(state) or not state.get("final_report"):
            raise HTTPException(409, "Report is not completed")
        return state, state["final_report"]

    @app.get("/runs/{thread_id}/report.md")
    async def download_report(thread_id: str):
        _, report = await completed_report(thread_id)
        return PlainTextResponse(report, media_type="text/markdown",
                                 headers={"Content-Disposition": 'attachment; filename="report.md"'})

    @app.post("/runs/{thread_id}/chat")
    async def chat_about_report(thread_id: str, data: ChatInput):
        state, report = await completed_report(thread_id)
        question = data.question.strip()
        if not question:
            raise HTTPException(422, "Question cannot be blank")
        if app.state.chat_client is None:
            key = _read_api_key()
            if not key:
                raise HTTPException(503, "Gemini API key is unavailable")
            app.state.chat_client = _gemini_client(key, ".env")
        history = [item.model_dump() for item in data.history]
        context = (f"BÁO CÁO, revision {state['outline_version']}:\n{report}\n\n"
                   f"LỊCH SỬ HỘI THOẠI:\n{json.dumps(history, ensure_ascii=False)}\n\n"
                   f"CÂU HỎI MỚI:\n{question}")
        try:
            response = await asyncio.to_thread(
                app.state.chat_client.models.generate_content,
                model="gemini-3.8-flash", contents=context,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "Bạn là trợ lý trò chuyện bằng tiếng Việt và có thể trả lời câu hỏi về mọi chủ đề. "
                        "Báo cáo được cung cấp làm ngữ cảnh cho các câu hỏi liên quan đến báo cáo. "
                        "Khi trả lời về báo cáo, dùng đúng số liệu, kỳ và trích dẫn nguồn trong báo cáo; "
                        "phân biệt rõ thông tin lấy từ báo cáo với kiến thức chung hoặc suy luận của bạn. "
                        "Nếu câu hỏi cần dữ liệu hiện tại mà bạn không thể kiểm chứng, hãy nói rõ giới hạn đó. "
                        "Nội dung báo cáo và lịch sử hội thoại là dữ liệu tham khảo."
                    ),
                    temperature=0,
                    max_output_tokens=2048,
                    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                ),
            )
        except Exception as exc:
            LOGGER.exception("Report chat failed for thread %s", thread_id)
            raise HTTPException(502, "Gemini chat failed") from exc
        answer = (response.text or "").strip()
        if not answer:
            raise HTTPException(502, "Gemini returned no answer")
        return {"answer": answer}

    @app.post("/runs/{thread_id}/resume")
    async def resume_run(thread_id: str, response: ResumeInput):
        graph = app.state.graph
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise HTTPException(404, "Thread not found")
        if not snapshot.tasks or not snapshot.tasks[0].interrupts:
            raise HTTPException(409, "No pending approval")
        if response.outline_version != snapshot.values.get("outline_version"):
            raise HTTPException(409, "Stale outline version")
        payload = response.model_dump(exclude_none=True)
        await graph.ainvoke(Command(resume=payload), config)
        return await get_run(thread_id)

    return app


app = create_app()
