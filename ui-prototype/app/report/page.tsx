"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { CitationText } from "../components/citation-text";
import { MarkdownTable } from "../components/markdown-table";

type ReportSnapshot = {
  request: { ticker: string; start_year: number; end_year: number; scope: string };
  outline_version: number | null;
  run_status: string;
  final_report: string | null;
};
type ChatMessage = { role: "user" | "assistant"; content: string };

function ReportContent({ markdown }: { markdown: string }) {
  const blocks = markdown.trim().split(/\n\s*\n/);
  const sections = blocks.map((block, index) => ({ block, index }))
    .filter(({ block }) => block.startsWith("## "));
  return <>
    <nav className="report-index" aria-label="Mục lục báo cáo">
      <span>Trong báo cáo</span>
      {sections.map(({ block, index }) => <a href={`#section-${index}`} key={index}>{block.slice(3)}</a>)}
    </nav>
    <article className="report-content">{blocks.map((block, index) => {
      if (block.startsWith("## ")) return <h2 id={`section-${index}`} key={index}>{block.slice(3)}</h2>;
      if (block.startsWith("### ")) return <h3 key={index}>{block.slice(4)}</h3>;
      if (block.startsWith("|")) return <MarkdownTable key={index} markdown={block} />;
      return <p key={index}><CitationText text={block} /></p>;
    })}</article>
  </>;
}

function ReportChat({ threadId }: { threadId: string }) {
  const storageKey = `report-chat-${threadId}`;
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
      return Array.isArray(saved) ? saved.filter((item): item is ChatMessage =>
        (item?.role === "user" || item?.role === "assistant") && typeof item.content === "string") : [];
    } catch { return []; }
  });
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const messagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [messages, busy]);

  async function ask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuestion = question.trim();
    if (!nextQuestion || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/report/chat", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ threadId, question: nextQuestion, history: messages.slice(-12) }),
      });
      const body = await response.json();
      if (!response.ok || typeof body.answer !== "string") {
        throw new Error(typeof body.detail === "string" ? body.detail : "Không nhận được câu trả lời");
      }
      const updated: ChatMessage[] = [...messages, { role: "user", content: nextQuestion },
        { role: "assistant", content: body.answer }];
      setMessages(updated);
      setQuestion("");
      try { localStorage.setItem(storageKey, JSON.stringify(updated)); }
      catch { setError("Không lưu được lịch sử chat trên trình duyệt."); }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thể gửi câu hỏi");
    } finally { setBusy(false); }
  }

  return <section className="report-chat" aria-label="Chat với Gemini">
    <div className="chat-intro"><div><div className="eyebrow">Trợ lý AI · Gemini 3.8 Flash</div>
      <h2>Trao đổi về báo cáo</h2>
      <p>Hỏi về số liệu, nguồn trích dẫn hoặc bất kỳ chủ đề nào khác. Báo cáo này được gửi làm ngữ cảnh cho mỗi câu hỏi.</p></div></div>
    <div className="chat-messages" aria-live="polite" ref={messagesRef}>
      {messages.length === 0 && <div className="chat-empty">Bạn có thể bắt đầu bằng: “Doanh thu năm 2025 là bao nhiêu, nguồn ở đâu?”</div>}
      {messages.map((message, index) => <div className={`chat-message ${message.role}`} key={index}>
        <strong>{message.role === "user" ? "Bạn" : "Gemini"}</strong>
        {message.role === "assistant"
          ? <div className="chat-markdown"><Streamdown mode="static" controls={false}>{message.content}</Streamdown></div>
          : <p>{message.content}</p>}
      </div>)}
      {busy && <p className="hint">Gemini đang trả lời…</p>}
    </div>
    <form onSubmit={ask} className="chat-form"><label htmlFor="report-question">Câu hỏi</label>
      <textarea id="report-question" value={question} onChange={event => setQuestion(event.target.value)} rows={2} maxLength={2000} placeholder="Nhập câu hỏi của bạn…" required />
      <button disabled={busy || !question.trim()}>Gửi câu hỏi <span aria-hidden="true">↗</span></button></form>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}

export default function ReportPage() {
  const [loaded, setLoaded] = useState<{ threadId: string; snapshot: ReportSnapshot } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const threadId = new URLSearchParams(window.location.search).get("threadId")
      || localStorage.getItem("planner-ui-thread");
    if (!threadId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError("Không tìm thấy mã phiên. Hãy mở báo cáo từ trang quy trình.");
      return;
    }
    const controller = new AbortController();
    fetch(`/api/report?threadId=${encodeURIComponent(threadId)}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? "Không đọc được phiên báo cáo");
        if (body.run_status !== "completed" || !body.final_report) {
          throw new Error("Phiên này chưa có báo cáo hoàn chỉnh.");
        }
        setLoaded({ threadId, snapshot: body as ReportSnapshot });
      })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Không mở được báo cáo"); });
    return () => controller.abort();
  }, []);

  const snapshot = loaded?.snapshot;
  function startNewReport() {
    localStorage.setItem("planner-ui-thread", crypto.randomUUID());
    window.location.assign("/");
  }
  return <main className="report-page">
    <header className="topbar"><div className="topbar-brand"><span className="brand-mark">RW</span><strong>Report Writer</strong><span className="tag">Báo cáo</span></div>
      <div className="report-nav"><Link className="secondary nav-link" href={loaded ? `/?threadId=${encodeURIComponent(loaded.threadId)}` : "/"}>← Quay lại quy trình</Link>
        <button onClick={startNewReport}>+ Lập báo cáo mới</button></div></header>
    {!snapshot ? <div className="report-loading card">{error || "Đang mở báo cáo…"}</div> : <div className="report-shell">
      <div className="report-hero"><div className="eyebrow">Báo cáo đã hoàn tất · Verifier đầy đủ</div>
        <h1>{snapshot.request.ticker} <span>· Báo cáo tài chính</span></h1>
        <div className="report-meta"><span>{snapshot.request.start_year}–{snapshot.request.end_year}</span>
          <span>{snapshot.request.scope === "consolidated" ? "Hợp nhất" : snapshot.request.scope === "separate" ? "Riêng" : "Chung"}</span>
          <span>Revision {snapshot.outline_version}</span></div>
      </div>
      <section className="report-paper" aria-label="Nội dung báo cáo hoàn chỉnh">
        <div className="report-paper-head"><div><div className="eyebrow">Nội dung đã kiểm chứng</div><h2>Báo cáo hoàn chỉnh</h2></div>
          <a className="download-link" href={`/api/report/download?threadId=${encodeURIComponent(loaded.threadId)}`}>↓ Tải Markdown</a></div>
        <ReportContent markdown={snapshot.final_report!} />
      </section>
      <ReportChat threadId={loaded.threadId} />
    </div>}
  </main>;
}
