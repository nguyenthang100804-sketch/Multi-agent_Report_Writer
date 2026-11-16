"""Visualize the LangGraph workflow with xray=True subgraphs using LangChain."""
from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib_cache"))

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables.graph import CurveStyle, Graph, NodeStyles
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.agents.draft_rendering import render_block
from src.agents.report_tables import render_section_tables
from src.agents.state import (
    ReportState,
    approve_outline_revision,
    can_complete,
    complete_run,
    install_outline_revision,
    report_checkpoint_serde,
    state_from_json,
)
from src.agents.verification import (
    attach_code_limitations,
    render_section_citations,
    verify_section_deterministically,
)
from src.schemas.report_schema import ReportOutline, SectionDraft

ROOT = Path(__file__).resolve().parents[2]


def build_xray_report_graph(*, require_outline_approval: bool = True, checkpointer=None):
    """Build the Report StateGraph with compiled Agent Subgraphs so get_graph(xray=True) shows internal nodes."""
    sample = state_from_json(
        (ROOT / "docs/examples/synthetic-report-state.json").read_text(encoding="utf-8")
    )

    # --- 1. Subgraph: planner ---
    planner_sg = StateGraph(ReportState)
    planner_sg.add_node("preflight", lambda state: {"run_status": "running"})
    planner_sg.add_node("toolbox", lambda state: {})
    planner_sg.add_node(
        "llm_propose",
        lambda state: {
            "outline": sample["outline"],
            "outline_version": 1,
            "outlines_by_revision": {1: sample["outline"].model_copy(deep=True)},
        },
    )
    planner_sg.add_node(
        "validate_outline",
        lambda state: {
            "planner_used_fallback": False,
            "run_status": "awaiting_approval" if require_outline_approval else "running",
        },
    )
    planner_sg.add_node(
        "template_fallback",
        lambda state: {
            "planner_used_fallback": True,
            "run_status": "awaiting_approval" if require_outline_approval else "running",
        },
    )
    planner_sg.add_edge(START, "preflight")
    planner_sg.add_edge("preflight", "toolbox")
    planner_sg.add_edge("toolbox", "llm_propose")
    planner_sg.add_conditional_edges(
        "llm_propose",
        lambda state: "validate_outline",
        {"toolbox": "toolbox", "validate_outline": "validate_outline"},
    )
    planner_sg.add_conditional_edges(
        "validate_outline",
        lambda state: END,
        {"llm_propose": "llm_propose", "template_fallback": "template_fallback", END: END},
    )
    planner_sg.add_edge("template_fallback", END)

    # --- 2. Node: approval (human-in-the-loop) ---
    def approval_node(state: ReportState) -> dict:
        response = interrupt(
            {
                "outline": state["outline"].model_dump(mode="json"),
                "outline_version": state["outline_version"],
            }
        )
        if response.get("action") == "approve":
            return {**approve_outline_revision(state), "run_status": "running"}
        if response.get("action") == "revise":
            revised = ReportOutline.model_validate(response.get("outline"))
            return {**install_outline_revision(state, revised), "run_status": "awaiting_approval"}
        return {"run_status": "needs_clarification"}

    # --- 3. Subgraph: researcher ---
    researcher_sg = StateGraph(ReportState)
    researcher_sg.add_node("check_cache", lambda state: {})
    researcher_sg.add_node(
        "query_facts",
        lambda state: {
            "research_results": sample["research_results"],
            "evidence_by_id": sample["evidence_by_id"],
        },
    )
    researcher_sg.add_node("search_notes", lambda state: {})
    researcher_sg.add_node(
        "compute_metrics",
        lambda state: {"calculations_by_id": sample["calculations_by_id"]},
    )
    researcher_sg.add_node(
        "assign_aliases",
        lambda state: {
            "evidence_aliases": {
                "E1": next(
                    key
                    for key, record in sample["evidence_by_id"].items()
                    if record.payload.fiscal_year == 2024
                )
            }
        },
    )
    researcher_sg.add_edge(START, "check_cache")
    researcher_sg.add_edge("check_cache", "query_facts")
    researcher_sg.add_edge("check_cache", "search_notes")
    researcher_sg.add_edge("query_facts", "compute_metrics")
    researcher_sg.add_edge("search_notes", "compute_metrics")
    researcher_sg.add_edge("compute_metrics", "assign_aliases")
    researcher_sg.add_edge("assign_aliases", END)

    # --- 4. Subgraph: writer ---
    def _draft_quant(state: ReportState) -> dict:
        block = render_block(
            "revenue_block",
            "Doanh thu đạt {{E1}}.",
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["evidence_aliases"],
        )
        draft = SectionDraft(
            section_id="revenue",
            outline_version=state["outline_version"],
            revision=1,
            blocks=[block],
        )
        return {"section_drafts": {("revenue", 1): draft}}

    def _render_blocks(state: ReportState) -> dict:
        sections = {s.section_id: s for s in state["outline"].sections}
        drafts = {
            key: attach_code_limitations(
                draft,
                sections[draft.section_id],
                state.get("calculations_by_id", {}),
                state.get("research_results", {}),
            )
            for key, draft in state.get("section_drafts", {}).items()
        }
        return {"section_drafts": drafts} if drafts else {}

    writer_sg = StateGraph(ReportState)
    writer_sg.add_node("build_menu", lambda state: {})
    writer_sg.add_node("draft_quant", _draft_quant)
    writer_sg.add_node("draft_qual", lambda state: {})
    writer_sg.add_node("validate_tokens", lambda state: {})
    writer_sg.add_node("template_fallback", lambda state: {})
    writer_sg.add_node("render_blocks", _render_blocks)
    writer_sg.add_edge(START, "build_menu")
    writer_sg.add_edge("build_menu", "draft_quant")
    writer_sg.add_edge("build_menu", "draft_qual")
    writer_sg.add_edge("draft_quant", "validate_tokens")
    writer_sg.add_conditional_edges(
        "validate_tokens",
        lambda state: "render_blocks",
        {
            "draft_quant": "draft_quant",
            "template_fallback": "template_fallback",
            "render_blocks": "render_blocks",
        },
    )
    writer_sg.add_edge("template_fallback", "render_blocks")
    writer_sg.add_edge("draft_qual", "render_blocks")
    writer_sg.add_edge("render_blocks", END)

    # --- 5. Subgraph: verifier ---
    def _deterministic_check(state: ReportState) -> dict:
        results = {}
        for section in state["outline"].sections:
            drafts = [
                d
                for d in state.get("section_drafts", {}).values()
                if d.section_id == section.section_id and d.outline_version == state["outline_version"]
            ]
            if not drafts:
                continue
            draft = max(drafts, key=lambda item: item.revision)
            res = verify_section_deterministically(
                draft,
                state["request"],
                state.get("evidence_by_id", {}),
                state.get("calculations_by_id", {}),
                state.get("research_results", {}),
                state.get("evidence_aliases", {}),
                section,
            ).model_copy(update={"outline_version": state["outline_version"]})
            key = (state["outline_version"], section.section_id, draft.revision)
            results[key] = res
        return {"verification_results": results}

    def _render_report(state: ReportState) -> dict:
        rendered = []
        for section in state["outline"].sections:
            drafts = [
                d
                for d in state.get("section_drafts", {}).values()
                if d.section_id == section.section_id and d.outline_version == state["outline_version"]
            ]
            if not drafts:
                continue
            draft = max(drafts, key=lambda item: item.revision)
            key = (state["outline_version"], section.section_id, draft.revision)
            result = state.get("verification_results", {}).get(key)
            if result and result.status == "passed":
                prose = render_section_citations(
                    draft,
                    state.get("evidence_by_id", {}),
                    state.get("calculations_by_id", {}),
                    state.get("research_results", {}),
                    section,
                )
                tables = render_section_tables(section, state)
                if tables and prose.startswith("## "):
                    heading, sep, rem = prose.partition("\n\n")
                    prose = heading + "\n\n" + tables + (sep + rem if rem else "")
                rendered.append(prose)
        status_update = complete_run(state) if can_complete(state) else {"run_status": "incomplete"}
        return {"final_report": "\n\n".join(rendered) or None, **status_update}

    verifier_sg = StateGraph(ReportState)
    verifier_sg.add_node("deterministic_check", _deterministic_check)
    verifier_sg.add_node("semantic_llm_check", lambda state: {})
    verifier_sg.add_node("render_report", _render_report)
    verifier_sg.add_edge(START, "deterministic_check")
    verifier_sg.add_conditional_edges(
        "deterministic_check",
        lambda state: "render_report",
        {"semantic_llm_check": "semantic_llm_check", "render_report": "render_report"},
    )
    verifier_sg.add_edge("semantic_llm_check", "render_report")
    verifier_sg.add_edge("render_report", END)

    # --- Root StateGraph ---
    root = StateGraph(ReportState)
    root.add_node("planner", planner_sg.compile())
    if require_outline_approval:
        root.add_node("approval", approval_node)
    root.add_node("researcher", researcher_sg.compile())
    root.add_node("writer", writer_sg.compile())
    root.add_node("verifier", verifier_sg.compile())

    root.add_edge(START, "planner")
    planner_routes = (
        {"approval": "approval", "researcher": "researcher", END: END}
        if require_outline_approval
        else {"researcher": "researcher", END: END}
    )
    root.add_conditional_edges(
        "planner",
        lambda state: (
            "approval"
            if state["run_status"] == "awaiting_approval"
            else "researcher"
            if state["run_status"] == "running"
            else END
        ),
        planner_routes,
    )
    if require_outline_approval:
        root.add_conditional_edges(
            "approval",
            lambda state: (
                "approval"
                if state["run_status"] == "awaiting_approval"
                else "researcher"
                if state["run_status"] == "running"
                else END
            ),
            {"approval": "approval", "researcher": "researcher", END: END},
        )
    root.add_edge("researcher", "writer")
    root.add_edge("writer", "verifier")
    root.add_edge("verifier", END)
    return root.compile(checkpointer=checkpointer)


class XrayGraphTracer(BaseCallbackHandler):
    """LangChain CallbackHandler that records exact subgraph node transitions (`agent:subnode`)."""

    def __init__(self, valid_node_ids: set[str]) -> None:
        super().__init__()
        self.valid_node_ids = valid_node_ids
        self.active_runs: dict[UUID, tuple[str, float]] = {}
        self.visited_nodes: list[str] = []
        self.step_records: list[dict[str, Any]] = []

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        meta = metadata or {}
        node_name = meta.get("langgraph_node")
        run_name = kwargs.get("name")
        if not node_name or run_name != node_name:
            return
        checkpoint_ns = meta.get("checkpoint_ns", "")
        prefix = checkpoint_ns.split(":")[0] if ":" in checkpoint_ns else ""
        full_id = f"{prefix}:{node_name}" if prefix and f"{prefix}:{node_name}" in self.valid_node_ids else node_name
        if full_id in self.valid_node_ids:
            self.active_runs[run_id] = (full_id, time.perf_counter())
            self.visited_nodes.append(full_id)
            print(f"  [#{len(self.visited_nodes):02d}] ▶ {full_id}", flush=True)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if run_id not in self.active_runs:
            return
        full_id, started_at = self.active_runs.pop(run_id)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        self.step_records.append(
            {"step": len(self.step_records) + 1, "node": full_id, "duration_ms": round(elapsed_ms, 2), "state": "ok"}
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if run_id not in self.active_runs:
            return
        full_id, started_at = self.active_runs.pop(run_id)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if type(error).__name__ == "GraphInterrupt":
            self.step_records.append(
                {
                    "step": len(self.step_records) + 1,
                    "node": full_id,
                    "duration_ms": round(elapsed_ms, 2),
                    "state": "interrupt",
                }
            )


def build_xray_highlighted_mermaid(xray_graph: Graph, tracer: XrayGraphTracer) -> str:
    """Use LangChain's draw_mermaid() on the xray=True graph and highlight visited nodes."""
    base_mermaid = xray_graph.draw_mermaid(
        with_styles=True,
        curve_style=CurveStyle.LINEAR,
        node_colors=NodeStyles(
            first="fill:#fff9c4,stroke:#f57f17,stroke-width:2px",
            last="fill:#fff9c4,stroke:#f57f17,stroke-width:2px",
            default="fill:#ede7f6,stroke:#7e57c2,line-height:1.2",
        ),
    )
    lines = [line.rstrip() for line in base_mermaid.splitlines()]
    lines.append("	classDef executed fill:#a5d6a7,stroke:#1b5e20,stroke-width:2.5px,color:#000,font-weight:bold")
    visited_escaped = sorted({node_id.replace(":", "\\3a") for node_id in tracer.visited_nodes})
    if visited_escaped:
        lines.append(f"	class {','.join(visited_escaped)} executed")
    return "\n".join(lines) + "\n"


def render_xray_graph_png(xray_graph: Graph, tracer: XrayGraphTracer, output_path: Path) -> None:
    """Render the xray=True LangGraph as a clean node-and-edge graph with subgraph boxes."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    visited_set = set(tracer.visited_nodes)

    # Coordinates (x, y) for every node in the xray=True graph
    coords: dict[str, tuple[float, float]] = {
        "__start__": (50.0, 96.0),
        # Subgraph: planner
        "planner:preflight": (24.0, 84.0),
        "planner:toolbox": (42.0, 84.0),
        "planner:llm_propose": (60.0, 84.0),
        "planner:validate_outline": (78.0, 84.0),
        "planner:template_fallback": (78.0, 75.5),
        # Approval node
        "approval": (50.0, 64.0),
        # Subgraph: researcher
        "researcher:check_cache": (24.0, 50.0),
        "researcher:query_facts": (42.0, 53.5),
        "researcher:search_notes": (42.0, 46.5),
        "researcher:compute_metrics": (60.0, 50.0),
        "researcher:assign_aliases": (78.0, 50.0),
        # Subgraph: writer
        "writer:build_menu": (22.0, 31.5),
        "writer:draft_quant": (39.0, 35.0),
        "writer:draft_qual": (39.0, 27.0),
        "writer:validate_tokens": (57.0, 35.0),
        "writer:template_fallback": (57.0, 27.0),
        "writer:render_blocks": (78.0, 31.5),
        # Subgraph: verifier
        "verifier:deterministic_check": (30.0, 13.5),
        "verifier:semantic_llm_check": (54.0, 17.0),
        "verifier:render_report": (76.0, 13.5),
        # End
        "__end__": (50.0, 3.0),
    }

    subgraph_boxes = [
        ("subgraph: planner", 13.0, 71.5, 76.0, 18.0, "#f3e5f5", "#8e24aa"),
        ("subgraph: researcher", 13.0, 42.5, 76.0, 15.5, "#e3f2fd", "#1e88e5"),
        ("subgraph: writer", 13.0, 23.0, 76.0, 16.5, "#fff8e1", "#fb8c00"),
        ("subgraph: verifier", 18.0, 9.5, 70.0, 11.0, "#e0f2f1", "#00897b"),
    ]

    fig, ax = plt.subplots(figsize=(13, 15), dpi=160)
    ax.set_xlim(4, 96)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.set_title(
        "LangGraph X-Ray Flow (graph.get_graph(xray=True))",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )

    # 1. Draw subgraph containers
    for label, x, y, w, h, bg, border in subgraph_boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.3,rounding_size=0.8",
                facecolor=bg,
                edgecolor=border,
                linewidth=1.5,
                linestyle="--",
                alpha=0.55,
            )
        )
        ax.text(
            x + 1.2,
            y + h - 1.3,
            label,
            ha="left",
            va="top",
            fontsize=9.5,
            fontweight="bold",
            color=border,
        )

    # 2. Draw nodes first and store their patches so FancyArrowPatch clips exactly to box borders
    box_w, box_h = 13.5, 4.2
    node_patches: dict[str, FancyBboxPatch] = {}
    for node_id, (cx, cy) in coords.items():
        if node_id not in xray_graph.nodes and node_id not in ("__start__", "__end__"):
            continue
        short_label = node_id.split(":", 1)[-1]
        is_start_end = node_id in ("__start__", "__end__")
        is_visited = node_id in visited_set

        if is_start_end:
            fc, ec, lw = "#fff9c4", "#f57f17", 2.0
        elif is_visited:
            fc, ec, lw = "#a5d6a7", "#1b5e20", 2.2
        else:
            fc, ec, lw = "#ffffff", "#9e9e9e", 1.3

        patch = FancyBboxPatch(
            (cx - box_w / 2, cy - box_h / 2),
            box_w,
            box_h,
            boxstyle="round,pad=0.2,rounding_size=1.2" if is_start_end else "round,pad=0.2,rounding_size=0.5",
            facecolor=fc,
            edgecolor=ec,
            linewidth=lw,
            zorder=3,
        )
        ax.add_patch(patch)
        node_patches[node_id] = patch
        ax.text(
            cx,
            cy,
            short_label,
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold" if (is_visited or is_start_end) else "normal",
            color="#111111" if (is_visited or is_start_end) else "#616161",
            zorder=4,
        )

    # Determine which directed edges were actually traversed during runtime
    active_edges: set[tuple[str, str]] = {
        ("__start__", "planner:preflight"),
        ("planner:preflight", "planner:toolbox"),
        ("planner:toolbox", "planner:llm_propose"),
        ("planner:llm_propose", "planner:validate_outline"),
        ("researcher:check_cache", "researcher:query_facts"),
        ("researcher:check_cache", "researcher:search_notes"),
        ("researcher:query_facts", "researcher:compute_metrics"),
        ("researcher:search_notes", "researcher:compute_metrics"),
        ("researcher:compute_metrics", "researcher:assign_aliases"),
        ("researcher:assign_aliases", "writer:build_menu"),
        ("writer:build_menu", "writer:draft_quant"),
        ("writer:build_menu", "writer:draft_qual"),
        ("writer:draft_quant", "writer:validate_tokens"),
        ("writer:validate_tokens", "writer:render_blocks"),
        ("writer:draft_qual", "writer:render_blocks"),
        ("writer:render_blocks", "verifier:deterministic_check"),
        ("verifier:deterministic_check", "verifier:render_report"),
        ("verifier:render_report", "__end__"),
    }
    if "approval" in visited_set:
        active_edges.add(("planner:validate_outline", "approval"))
        active_edges.add(("approval", "researcher:check_cache"))
        if tracer.visited_nodes.count("approval") > 1:
            active_edges.add(("approval", "approval"))
    else:
        active_edges.add(("planner:validate_outline", "researcher:check_cache"))

    # 3. Draw edges from xray_graph.edges using patchA/patchB so arrowheads land cleanly on borders
    for edge in xray_graph.edges:
        u, v = edge.source, edge.target
        if u == "planner:__end__":
            u = "planner:validate_outline"
        if v == "planner:__end__":
            continue
        if u not in coords or v not in coords:
            continue
        # Skip drawing long cross-diagram abort edges to __end__ if not taken, to keep graph clean
        if v == "__end__" and u in ("planner:validate_outline", "approval") and (u, v) not in active_edges:
            continue
        if (u, v) == ("planner:validate_outline", "researcher:check_cache") and "approval" in visited_set:
            continue

        x1, y1 = coords[u]
        x2, y2 = coords[v]
        is_active = (u, v) in active_edges

        color = "#1b5e20" if is_active else "#8d8d8d"
        lw = 2.0 if is_active else 1.2
        style = "--" if edge.conditional else "-"

        if u == v:
            # Self-loop on approval (revise)
            ax.add_patch(
                FancyArrowPatch(
                    (x1 + box_w / 2, y1 + 0.8),
                    (x1 + box_w / 2, y1 - 0.8),
                    arrowstyle="-|>",
                    mutation_scale=13,
                    linewidth=lw,
                    linestyle="--",
                    color=color,
                    connectionstyle="arc3,rad=-1.5",
                    zorder=5,
                )
            )
            ax.text(
                x1 + box_w / 2 + 4.8,
                y1,
                "revise",
                fontsize=8,
                fontweight="bold",
                color=color,
                va="center",
            )
            continue

        rad = 0.0
        if (u, v) in (
            ("planner:llm_propose", "planner:toolbox"),
            ("planner:validate_outline", "planner:llm_propose"),
            ("writer:validate_tokens", "writer:draft_quant"),
        ):
            rad = -0.4
        elif (u, v) == ("writer:draft_qual", "writer:render_blocks"):
            rad = 0.25
        elif (u, v) == ("verifier:deterministic_check", "verifier:render_report"):
            rad = 0.22

        ax.add_patch(
            FancyArrowPatch(
                (x1, y1),
                (x2, y2),
                patchA=node_patches[u],
                patchB=node_patches[v],
                arrowstyle="-|>",
                mutation_scale=14,
                linewidth=lw,
                linestyle=style,
                color=color,
                connectionstyle=f"arc3,rad={rad}",
                shrinkA=2,
                shrinkB=2,
                zorder=5,
            )
        )

    legend_items = [
        Line2D([0], [0], marker="s", color="w", label="Node đã chạy (Executed)", markerfacecolor="#a5d6a7", markeredgecolor="#1b5e20", markersize=11),
        Line2D([0], [0], marker="s", color="w", label="Node dự phòng / không đi qua", markerfacecolor="#ffffff", markeredgecolor="#9e9e9e", markersize=11),
        Line2D([0], [0], color="#1b5e20", lw=2.2, label="Luồng chuyển tiếp đã đi qua"),
        Line2D([0], [0], color="#757575", lw=1.2, ls="--", label="Nhánh điều kiện / Retry / Fallback"),
    ]
    ax.legend(handles=legend_items, loc="lower right", frameon=True, fontsize=8.5)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def run_demo_with_visualization(
    *,
    require_approval: bool = True,
    revise_once: bool = True,
    output_dir: Path,
) -> dict[str, Path]:
    """Compile the X-Ray report graph, trace execution with LangChain callbacks, and export graphs."""
    sample = state_from_json(
        (ROOT / "docs/examples/synthetic-report-state.json").read_text(encoding="utf-8")
    )
    checkpointer = InMemorySaver(serde=report_checkpoint_serde()) if require_approval else None
    graph = build_xray_report_graph(
        require_outline_approval=require_approval,
        checkpointer=checkpointer,
    )

    # 1. Lấy đồ thị 2 cấp: cấp top-level (`xray=False`) và cấp mở rộng bên trong Agent (`xray=True`)
    top_graph = graph.get_graph(xray=False)
    xray_graph = graph.get_graph(xray=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Chạy graph và dùng LangChain CallbackHandler ghi lại từng sub-node đã đi qua
    tracer = XrayGraphTracer(valid_node_ids=set(xray_graph.nodes.keys()))
    run_config: dict[str, Any] = {
        "configurable": {"thread_id": "visualize-xray-graph"},
        "callbacks": [tracer],
    }

    print("=== CHẠY GRAPH & GHI NHẬN LUỒNG SUBGRAPH (xray=True) ===", flush=True)
    for _ in graph.stream({"request": sample["request"]}, run_config, stream_mode="updates", subgraphs=True):
        pass

    if require_approval:
        state_vals = graph.get_state(run_config).values
        if revise_once and state_vals.get("run_status") == "awaiting_approval":
            print("  [Interrupt] approval -> resume='revise'", flush=True)
            revised = state_vals["outline"].model_copy(deep=True)
            for _ in graph.stream(
                Command(
                    resume={
                        "action": "revise",
                        "outline_version": state_vals["outline_version"],
                        "outline": revised.model_dump(mode="json"),
                    }
                ),
                run_config,
                stream_mode="updates",
                subgraphs=True,
            ):
                pass
            state_vals = graph.get_state(run_config).values

        if state_vals.get("run_status") == "awaiting_approval":
            print("  [Interrupt] approval -> resume='approve'", flush=True)
            for _ in graph.stream(
                Command(
                    resume={
                        "action": "approve",
                        "outline_version": state_vals["outline_version"],
                    }
                ),
                run_config,
                stream_mode="updates",
                subgraphs=True,
            ):
                pass

    # 3. Xuất Mermaid chuẩn từ `graph.get_graph(xray=True).draw_mermaid()`
    static_mmd_path = output_dir / "report_graph_static.mmd"
    static_mmd_path.write_text(top_graph.draw_mermaid(), encoding="utf-8")

    xray_mermaid = build_xray_highlighted_mermaid(xray_graph, tracer)
    xray_mmd_path = output_dir / "report_graph_runtime_trace.mmd"
    xray_mmd_path.write_text(xray_mermaid, encoding="utf-8")

    # 4. Xuất ảnh PNG Graph (`xray=True`)
    png_path = output_dir / "report_graph_runtime_trace.png"
    render_xray_graph_png(xray_graph, tracer, png_path)

    # 5. Xuất file Markdown chứa Mermaid `xray=True`
    trace_md_path = output_dir / "report_graph_runtime_trace.md"
    md_content = (
        "# LangGraph Flow (`graph.get_graph(xray=True)`)\n\n"
        f"```mermaid\n{xray_mermaid}```\n"
    )
    trace_md_path.write_text(md_content, encoding="utf-8")

    return {
        "xray_png": png_path,
        "xray_mermaid": xray_mmd_path,
        "xray_markdown": trace_md_path,
        "top_level_mermaid": static_mmd_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vẽ đồ thị LangGraph mở rộng subgraphs bên trong từng Agent bằng get_graph(xray=True)."
    )
    parser.add_argument("--no-approval", action="store_true")
    parser.add_argument("--no-revise", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/report_output/graph_visualization",
    )
    args = parser.parse_args()

    outputs = run_demo_with_visualization(
        require_approval=not args.no_approval,
        revise_once=not args.no_revise,
        output_dir=args.output_dir,
    )
    print("\n=== ĐÃ XUẤT GRAPH (xray=True) ===", flush=True)
    for label, path in outputs.items():
        print(f"- {label}: {path}", flush=True)


if __name__ == "__main__":
    main()
