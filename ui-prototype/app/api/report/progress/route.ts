const backend = "http://127.0.0.1:8123";

export async function POST(request: Request) {
  const threadId = new URL(request.url).searchParams.get("threadId");
  if (!threadId) return Response.json({ detail: "Missing threadId" }, { status: 400 });
  try {
    const response = await fetch(`${backend}/runs/${encodeURIComponent(threadId)}/progress`, {
      method: "POST", cache: "no-store",
    });
    return new Response(await response.text(), {
      status: response.status, headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "Backend chưa chạy trên cổng 8123" }, { status: 503 });
  }
}

export async function GET(request: Request) {
  const threadId = new URL(request.url).searchParams.get("threadId");
  if (!threadId) return Response.json({ detail: "Missing threadId" }, { status: 400 });
  try {
    const response = await fetch(`${backend}/runs/${encodeURIComponent(threadId)}/progress`, {
      cache: "no-store", signal: request.signal,
    });
    if (!response.ok || !response.body) return new Response(null, { status: response.status });
    return new Response(response.body, {
      headers: { "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache, no-transform", "x-accel-buffering": "no" },
    });
  } catch {
    return Response.json({ detail: "Backend chưa chạy trên cổng 8123" }, { status: 503 });
  }
}
