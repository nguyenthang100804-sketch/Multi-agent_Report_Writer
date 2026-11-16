"use client";

import { useAgent, useCopilotKit, useInterrupt } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { MarkdownTable } from "./components/markdown-table";

type Scope = "consolidated" | "separate" | "general";
type ReportRequest = {
  ticker: string; start_year: number; end_year: number; audience: string;
  scope: Scope; instructions?: string | null;
};
type Task = { task_id: string; task_type: string; metric_name?: string; item_code?: string; query?: string };
type Section = {
  section_id: string; title: string; objective: string;
  research_tasks?: Task[];
  subsections?: Array<{ subsection_id: string; title: string }>;
  [key: string]: unknown;
};
type Outline = { outline_id: string; sections: Section[]; [key: string]: unknown };
type PlannerNote = { code: string; message: string; section_id?: string | null };
type OutlineDecision = { action: string; reason: string; template_section_ids: string[]; resulting_section_ids: string[]; observation_ids: string[] };
type Observation = { observation_id: string; tool_name: string; status: string; missing_years: number[]; warnings: string[]; safe_for_calculation: boolean };
type ResearchResult = { task_id: string; status: string; evidence_count: number;
  missing: Array<{ description: string; reason: string }>;
  warnings: string[]; issues: string[]; next_action: string };
type VerificationIssue = { error_type: string; reason: string; severity: string; action: string };
type WriterSection = { section_id: string; title: string; draft_revision: number | null;
  text: string | null; table_markdown: string; used_fallback: boolean | null; attempts: number | null;
  writer_errors: string[];
  verification_status: string | null; verification_level: string | null;
  verification_issues: VerificationIssue[]; semantic_called: boolean;
  semantic_status: string | null; verifier_error: string | null };
type Snapshot = {
  request: ReportRequest;
  outline: Outline | null;
  outline_version: number | null;
  outline_approved_version: number | null;
  run_status: string;
  pending_interrupt: boolean;
  planner_notes: PlannerNote[];
  available_scopes: Record<string, number[]>;
  outline_decisions: OutlineDecision[];
  planner_observations: Observation[];
  planner_used_fallback: boolean;
  research_completed: boolean;
  research_results: ResearchResult[];
  evidence_count: number;
  calculation_count: number;
  writer_completed: boolean;
  writer_sections: WriterSection[];
  final_report: string | null;
};
type Approval = { outline: Outline; outline_version: number; decisions: OutlineDecision[]; planner_notes: PlannerNote[] };
type PlannerProgress = { id: number; stage: string; message: string };

const statusLabels: Record<string, string> = {
  awaiting_approval: "Chờ duyệt", running: "Đang xử lý", completed: "Hoàn tất",
  incomplete: "Chưa hoàn tất", needs_clarification: "Cần làm rõ", rejected: "Đã từ chối",
};

function ResearchCard({ snapshot }: { snapshot: Snapshot }) {
  return <section className="card research-card" aria-label="Kết quả Researcher">
    <div className="eyebrow">Sau khi duyệt dàn ý</div>
    <h3>Kết quả Researcher</h3>
    <p>{snapshot.research_results.length} tác vụ tra cứu · {snapshot.evidence_count} bằng chứng · {snapshot.calculation_count} phép tính</p>
    {snapshot.research_results.length === 0 && <p className="hint">Dàn ý không có tác vụ tra cứu.</p>}
    <ul className="task-list">{snapshot.research_results.map(result => <li key={result.task_id}>
      <strong>{result.task_id}</strong> · {result.status} · {result.evidence_count} bằng chứng
      {result.next_action !== "continue" && <span> · bước tiếp: {result.next_action}</span>}
      {result.missing.map((item, i) => <div key={i}>Thiếu: {item.description} ({item.reason})</div>)}
      {result.warnings.map((warning, i) => <div key={`warning-${i}`}>Cảnh báo: {warning}</div>)}
      {result.issues.map((issue, i) => <div key={`issue-${i}`}>Vấn đề: {issue}</div>)}
    </li>)}</ul>
  </section>;
}

function TablePreview({ markdown, verified }: { markdown: string; verified: boolean }) {
  const tables = markdown.split(/(?=^### )/m).filter(Boolean);
  return <div className="table-preview">
    <p className="hint">Bảng từ dữ liệu Researcher · {verified ? "section đã đạt Verifier đầy đủ" : "đạt kiểm tra quy tắc, chưa kiểm chứng ngữ nghĩa đầy đủ"}.</p>
    {tables.map(block => <div key={block.split("\n", 1)[0]}>
      <h4>{block.slice(4).split("\n", 1)[0]}</h4>
      <MarkdownTable markdown={block} />
    </div>)}
  </div>;
}

function WriterCard({ snapshot }: { snapshot: Snapshot }) {
  const drafted = snapshot.writer_sections.filter(section => section.draft_revision !== null).length;
  return <section className="card writer-card" aria-label="Bản nháp Writer">
    <div className="eyebrow">Sau Researcher</div>
    <h3>Bản nháp Writer và kết quả Verifier</h3>
    <p className="hint">{drafted}/{snapshot.writer_sections.length} section có bản nháp. {snapshot.run_status === "completed" ? "Tất cả section đã đạt Verifier đầy đủ." : "Xem trạng thái kiểm chứng theo từng section."}</p>
    {snapshot.writer_sections.map(section => <details className="draft-section" key={section.section_id}>
      <summary>{section.section_id} · {section.title} · {section.draft_revision === null ? "chưa có bản nháp" : `bản nháp ${section.draft_revision}`}{section.verification_status && ` · ${section.verification_level === "full" ? "đầy đủ" : "quy tắc"}: ${section.verification_status}`}</summary>
      {section.text && <div className="draft-text">{section.text}</div>}
      {section.table_markdown && <TablePreview markdown={section.table_markdown} verified={section.verification_level === "full" && section.verification_status === "passed"} />}
      {section.draft_revision !== null && <p className="hint">
        Nguồn: {section.used_fallback === false ? "Gemini" : section.used_fallback ? "mẫu dự phòng" : "mẫu"}
        {section.attempts !== null && ` · ${section.attempts} lượt tạo`}
        {section.verification_status && ` · kiểm tra ${section.verification_level === "full" ? "đầy đủ" : "quy tắc"}: ${section.verification_status}`}
        {section.semantic_status && ` · Verifier ngữ nghĩa: ${section.semantic_status}`}
      </p>}
      {section.verifier_error && <p className="error">Verifier: {section.verifier_error}</p>}
      {section.writer_errors.length > 0 && <ul className="task-list">{section.writer_errors.map((error, i) =>
        <li key={i}>Writer: {error}</li>)}</ul>}
      {section.verification_issues.length > 0 && <ul className="task-list">{section.verification_issues.map((issue, i) =>
        <li key={i}>{issue.severity} · {issue.error_type} · {issue.action}: {issue.reason}</li>)}</ul>}
    </details>)}
  </section>;
}

function ReviewCard({ payload, snapshot, resolve, refresh, onApprovalStart, onApprovalFinish }: {
  payload: Approval;
  snapshot: Snapshot | null;
  resolve: (value: unknown) => Promise<unknown>;
  refresh: () => Promise<unknown>;
  onApprovalStart: () => Promise<void>;
  onApprovalFinish: () => void;
}) {
  const [sections, setSections] = useState(payload.outline.sections);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function edit(index: number, field: "title" | "objective", value: string) {
    setSections(current => current.map((section, i) => i === index ? { ...section, [field]: value } : section));
  }

  async function submit(action: "approve" | "revise" | "reject") {
    setBusy(true);
    setError("");
    const outline = { ...payload.outline, sections };
    try {
      if (action === "approve") await onApprovalStart();
      await resolve({ action, outline_version: payload.outline_version,
        ...(action === "revise" ? { outline } : {}) });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tiếp tục phiên");
    } finally {
      if (action === "approve") onApprovalFinish();
      setBusy(false);
    }
  }

  return <section className="card" aria-label="Duyệt dàn ý">
    <div className="eyebrow">Cần người duyệt · revision {payload.outline_version}</div>
    <h3>Dàn ý Planner đề xuất</h3>
    {snapshot?.planner_used_fallback && <div className="notice">Planner đã dùng dàn ý dự phòng. Xem ghi chú trước khi duyệt.</div>}
    {sections.map((section, index) => <div className="section-review" key={section.section_id}>
      <div className="section-id">{section.section_id} · {section.research_tasks?.length ?? 0} tác vụ nghiên cứu</div>
      <label>Tiêu đề<input value={section.title} onChange={event => edit(index, "title", event.target.value)} /></label>
      <label>Mục tiêu<textarea value={section.objective} onChange={event => edit(index, "objective", event.target.value)} rows={2} /></label>
      {!!section.subsections?.length && <p className="hint">Mục con: {section.subsections.map(item => item.title).join(" · ")}</p>}
      {!!section.research_tasks?.length && <ul className="task-list">{section.research_tasks.map(task =>
        <li key={task.task_id}>{task.task_id} · {task.task_type} {task.metric_name ?? task.item_code ?? task.query ?? ""}</li>)}</ul>}
    </div>)}
    {!!payload.decisions?.length && <div className="review-details"><h4>Quyết định của Planner</h4><ul>{payload.decisions.map((item, i) =>
      <li key={i}><strong>{item.action}</strong> {item.template_section_ids.join(", ")} → {item.resulting_section_ids.join(", ") || "bỏ"}: {item.reason} {item.observation_ids.length > 0 && <small>({item.observation_ids.join(", ")})</small>}</li>)}</ul></div>}
    {!!payload.planner_notes?.length && <div className="review-details"><h4>Ghi chú</h4><ul>{payload.planner_notes.map((note, i) => <li key={i}>{note.message}</li>)}</ul></div>}
    {!!snapshot?.planner_observations.length && <div className="review-details"><h4>Quan sát dữ liệu</h4><ul>{snapshot.planner_observations.map(item =>
      <li key={item.observation_id}>{item.observation_id} · {item.tool_name}: {item.status}{item.missing_years.length > 0 && ` · thiếu năm ${item.missing_years.join(", ")}`}{item.warnings.length > 0 && ` · ${item.warnings.join("; ")}`}</li>)}</ul></div>}
    <p className="hint">Có thể sửa tiêu đề và mục tiêu; tác vụ nghiên cứu được giữ nguyên. Lưu bản sửa để tạo revision mới.</p>
    <div className="actions">
      <button disabled={busy} onClick={() => submit("approve")}>{busy ? "Graph đang xử lý…" : "Duyệt dàn ý"}</button>
      <button className="secondary" disabled={busy || sections.some(item => !item.title.trim() || !item.objective.trim())} onClick={() => submit("revise")}>Lưu bản sửa</button>
      <button className="text-button" disabled={busy} onClick={() => submit("reject")}>Từ chối</button>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}

function ApprovalInterrupt({ snapshot, refresh, reportBusy, onApprovalStart, onApprovalFinish }: {
  snapshot: Snapshot | null;
  refresh: () => Promise<Snapshot | null>;
  reportBusy: boolean;
  onApprovalStart: () => Promise<void>;
  onApprovalFinish: () => void;
}) {
  const interrupt = useInterrupt({
    agentId: "report_probe_session", renderInChat: false,
    render: ({ event, resolve }) => {
      const payload = (typeof event.value === "string" ? JSON.parse(event.value) : event.value) as Approval;
      return <ReviewCard key={payload.outline_version} payload={payload} snapshot={snapshot}
        resolve={resolve} refresh={refresh} onApprovalStart={onApprovalStart} onApprovalFinish={onApprovalFinish} />;
    },
  });
  return reportBusy ? null : <>{interrupt}{snapshot?.pending_interrupt && !interrupt &&
    <p className="hint">Đang tải thẻ duyệt từ CopilotKit…</p>}</>;
}

function Workspace({ threadId, initialRequest, newThread }: {
  threadId: string; initialRequest: ReportRequest | null;
  newThread: (request?: ReportRequest) => void;
}) {
  const { agent, isReady } = useAgent({ agentId: "report_probe_session", runtimeAgentId: "report_probe", threadId });
  const { copilotkit } = useCopilotKit();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [ticker, setTicker] = useState(initialRequest?.ticker ?? "HUT");
  const [startYear, setStartYear] = useState(initialRequest?.start_year ?? 2022);
  const [endYear, setEndYear] = useState(initialRequest?.end_year ?? 2025);
  const [scope, setScope] = useState<Scope>(initialRequest?.scope ?? "consolidated");
  const [instructions, setInstructions] = useState(initialRequest?.instructions ?? "");
  const [busy, setBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [progressEvents, setProgressEvents] = useState<PlannerProgress[]>([]);
  const [progressReady, setProgressReady] = useState(false);
  const [progressError, setProgressError] = useState(false);
  const [error, setError] = useState("");
  const loaded = useRef(false);
  const progressList = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (progressList.current) progressList.current.scrollTop = progressList.current.scrollHeight;
  }, [progressEvents]);

  useEffect(() => {
    if ((!busy && !reportBusy) || !progressReady) return;
    const stream = new EventSource(`/api/report/progress?threadId=${encodeURIComponent(threadId)}`);
    stream.onopen = () => setProgressError(false);
    stream.onmessage = event => {
      const item = JSON.parse(event.data) as PlannerProgress;
      if (typeof item.id !== "number" || typeof item.message !== "string") return;
      setProgressEvents(current => current.some(entry => entry.id === item.id) ? current :
        [...current, item].slice(-18));
    };
    stream.onerror = () => setProgressError(true);
    return () => stream.close();
  }, [busy, reportBusy, progressReady, threadId]);

  const refresh = useCallback(async () => {
    const response = await fetch(`/api/report?threadId=${encodeURIComponent(threadId)}`, { cache: "no-store" });
    if (response.status === 404) { setSnapshot(null); return null; }
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail ?? "Không đọc được phiên");
    setSnapshot(body as Snapshot);
    return body as Snapshot;
  }, [threadId]);

  useEffect(() => {
    if (!isReady || loaded.current) return;
    loaded.current = true;
    refresh().then(saved => {
      if (saved?.pending_interrupt) return copilotkit.runAgent({ agent });
    }).catch(cause => setError(cause instanceof Error ? cause.message : "Không thể mở phiên"));
  }, [agent, copilotkit, isReady, refresh]);

  const onApprovalStart = useCallback(async () => {
    setReportBusy(true); setError(""); setProgressEvents([]);
    setProgressReady(false); setProgressError(false);
    const response = await fetch(`/api/report/progress?threadId=${encodeURIComponent(threadId)}`, { method: "POST" });
    if (!response.ok) throw new Error("Không thể mở luồng tiến trình tạo báo cáo");
    setProgressEvents([{ id: 0, stage: "approved", message: "Đang gửi quyết định duyệt dàn ý" }]);
    setProgressReady(true);
  }, [threadId]);

  const onApprovalFinish = useCallback(() => {
    setReportBusy(false); setProgressReady(false);
  }, []);

  async function start(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isReady) return;
    setBusy(true); setError(""); setProgressEvents([]); setProgressReady(false); setProgressError(false);
    try {
      const progressResponse = await fetch(`/api/report/progress?threadId=${encodeURIComponent(threadId)}`, { method: "POST" });
      if (!progressResponse.ok) throw new Error("Không thể mở luồng tiến trình Planner");
      setProgressEvents([{ id: 0, stage: "submitted", message: "Đã gửi yêu cầu lập dàn ý" }]);
      setProgressReady(true);
      agent.setState({ request: { ticker, start_year: startYear, end_year: endYear,
        audience: initialRequest?.audience ?? "Nhà đầu tư",
        scope, instructions: instructions.trim() || null,
        report_type: "multi_year_financial_analysis", language: "vi" } });
      await copilotkit.runAgent({ agent });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể tạo phiên");
    } finally { setBusy(false); setProgressReady(false); }
  }

  return <main>
    <header className="topbar"><div className="topbar-brand"><span className="brand-mark">RW</span><strong>Report Writer</strong><span className="tag">Không gian làm việc</span></div><button className="secondary" onClick={() => newThread()}>+ Phiên mới</button></header>
    <div className="layout">
      <aside><div className="eyebrow">Các bước thực hiện</div><h1>Lập báo cáo tài chính</h1>
        <p>Nhập yêu cầu, duyệt dàn ý và xem kết quả sau khi báo cáo được tạo.</p>
        <ol><li><span>01</span> Tạo yêu cầu</li><li><span>02</span> Duyệt dàn ý</li><li><span>03</span> Tạo và kiểm chứng</li><li><span>04</span> Xem báo cáo</li></ol>
        <div className="thread-id"><small>Mã phiên</small><code>{threadId}</code></div>
      </aside>
      <section className="main-panel"><div className="heading"><div><div className="eyebrow">Bảng điều khiển</div><h2>Phiên lập báo cáo</h2><p className="hint">Theo dõi tiến trình từ dàn ý đến kết quả đã kiểm chứng.</p></div><span className={`status status-${busy || reportBusy ? "running" : snapshot?.run_status ?? "idle"}`}>{reportBusy ? "Đang tạo và kiểm chứng" : busy ? "Đang lập dàn ý" : snapshot ? (statusLabels[snapshot.run_status] ?? snapshot.run_status) : (isReady ? "Chưa bắt đầu" : "Đang kết nối")}</span></div>
        {!snapshot && <form className="card" onSubmit={start}><div className="grid">
          <label>Mã doanh nghiệp<input value={ticker} onChange={event => setTicker(event.target.value.toUpperCase())} required /></label>
          <label>Phạm vi<select value={scope} onChange={event => setScope(event.target.value as Scope)}><option value="consolidated">Hợp nhất</option><option value="separate">Riêng</option><option value="general">Chung</option></select></label>
          <label>Từ năm<input type="number" value={startYear} onChange={event => setStartYear(Number(event.target.value))} required /></label>
          <label>Đến năm<input type="number" min={startYear} value={endYear} onChange={event => setEndYear(Number(event.target.value))} required /></label>
        </div><label>Yêu cầu bổ sung<textarea value={instructions} onChange={event => setInstructions(event.target.value)} rows={3} /></label>
          <button disabled={busy || !isReady}>{busy ? "Planner đang xử lý…" : "Lập dàn ý"}</button></form>}
        {(busy || reportBusy) && <section className="planner-progress" aria-label={reportBusy ? "Tiến trình tạo báo cáo" : "Tiến trình Planner"} aria-live="polite">
          <div className="planner-progress-head"><span className="planner-progress-dot" aria-hidden="true" /><strong>{reportBusy ? "Đang tạo và kiểm chứng báo cáo" : "Planner đang xử lý yêu cầu"}</strong></div>
          {progressEvents.length === 0 ? <p>Đang kết nối với backend…</p> :
            <ol ref={progressList}>{progressEvents.map((item, index) => <li key={item.id} className={index === progressEvents.length - 1 ? "current" : ""}>{item.message}</li>)}</ol>}
          {progressError && <p className="error">Mất kết nối cập nhật tiến trình. Đang thử kết nối lại…</p>}
        </section>}
        {snapshot && <div className="summary"><strong>{snapshot.request.ticker}</strong><span>{snapshot.request.start_year}–{snapshot.request.end_year}</span><span>{snapshot.request.scope === "consolidated" ? "Hợp nhất" : snapshot.request.scope === "separate" ? "Riêng" : "Chung"}</span>{snapshot.outline_version && <span>Revision {snapshot.outline_version}</span>}</div>}
        {isReady && <ApprovalInterrupt snapshot={snapshot} refresh={refresh} reportBusy={reportBusy}
          onApprovalStart={onApprovalStart} onApprovalFinish={onApprovalFinish} />}
        {snapshot?.pending_interrupt && !isReady && <p className="hint">Đang kết nối để tải thẻ duyệt…</p>}
        {snapshot?.run_status === "completed" && <div className="completion-card"><div className="completion-icon" aria-hidden="true">✓</div>
          <div><div className="eyebrow">Đã kiểm chứng đầy đủ</div><h3>Báo cáo đã sẵn sàng</h3>
            <p>Tất cả section của revision đã duyệt đều đạt Verifier. Mở trang báo cáo để đọc nội dung và trao đổi với Gemini.</p>
            <Link className="primary-link" href={`/report?threadId=${encodeURIComponent(threadId)}`}>Mở báo cáo hoàn chỉnh <span aria-hidden="true">↗</span></Link></div></div>}
        {snapshot?.run_status === "incomplete" && <div className="notice">{snapshot.writer_completed ? "Bản nháp đã được tạo; một hoặc nhiều section chưa đạt Verifier đầy đủ. Xem kết quả theo section." : "Phiên này chưa có bản nháp Writer được kiểm chứng."}</div>}
        {snapshot?.run_status === "completed" ? <details className="diagnostics"><summary>Xem các bước tạo và kiểm chứng báo cáo</summary>
          {snapshot.writer_completed && <WriterCard snapshot={snapshot} />}
          {snapshot.research_completed && <ResearchCard snapshot={snapshot} />}
        </details> : <>
          {snapshot?.writer_completed && <WriterCard snapshot={snapshot} />}
          {snapshot?.research_completed && <ResearchCard snapshot={snapshot} />}
        </>}
        {(snapshot?.run_status === "needs_clarification" || snapshot?.run_status === "rejected") && <div className="notice">
          <strong>{snapshot.outline ? "Dàn ý đã bị từ chối" : snapshot.run_status === "rejected" ? "Planner không thể lập dàn ý" : "Cần làm rõ yêu cầu"}</strong>
          <ul>{snapshot.planner_notes.map((note, i) => <li key={i}>{note.message}</li>)}</ul>
          {Object.keys(snapshot.available_scopes).length > 0 && <p>Phạm vi có dữ liệu: {Object.entries(snapshot.available_scopes).map(([name, years]) => `${name} (${years.join(", ")})`).join("; ")}</p>}
          <button className="secondary" onClick={() => newThread(snapshot.request)}>Sửa yêu cầu trong phiên mới</button>
        </div>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>
    </div>
  </main>;
}

export default function Home() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ReportRequest | null>(null);
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("threadId");
    let saved = fromUrl || localStorage.getItem("planner-ui-thread");
    if (!saved) { saved = crypto.randomUUID(); localStorage.setItem("planner-ui-thread", saved); }
    if (fromUrl) { localStorage.setItem("planner-ui-thread", saved); window.history.replaceState(window.history.state, "", "/"); }
    // Restore browser-only state after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThreadId(saved);
  }, []);
  function newThread(request?: ReportRequest) { const id = crypto.randomUUID(); localStorage.setItem("planner-ui-thread", id); setDraft(request ?? null); setThreadId(id); }
  return threadId ? <Workspace key={threadId} threadId={threadId} initialRequest={draft} newThread={newThread} /> : null;
}
