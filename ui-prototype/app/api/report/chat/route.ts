export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.threadId !== "string") {
    return Response.json({ detail: "Missing threadId" }, { status: 400 });
  }
  try {
    const response = await fetch(`http://127.0.0.1:8123/runs/${encodeURIComponent(body.threadId)}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: body.question, history: body.history }),
      cache: "no-store",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "Backend chưa chạy trên cổng 8123" }, { status: 503 });
  }
}
