export async function GET(request: Request) {
  const threadId = new URL(request.url).searchParams.get("threadId");
  if (!threadId) return Response.json({ detail: "Missing threadId" }, { status: 400 });
  try {
    const response = await fetch(`http://127.0.0.1:8123/runs/${encodeURIComponent(threadId)}`, {
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
