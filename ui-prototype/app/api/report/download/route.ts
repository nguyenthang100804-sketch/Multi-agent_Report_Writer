export async function GET(request: Request) {
  const threadId = new URL(request.url).searchParams.get("threadId");
  if (!threadId) return Response.json({ detail: "Missing threadId" }, { status: 400 });
  try {
    const response = await fetch(`http://127.0.0.1:8123/runs/${encodeURIComponent(threadId)}/report.md`, {
      cache: "no-store",
    });
    const headers = new Headers({ "content-type": response.headers.get("content-type") ?? "text/plain" });
    const disposition = response.headers.get("content-disposition");
    if (disposition) headers.set("content-disposition", disposition);
    return new Response(response.body, { status: response.status, headers });
  } catch {
    return Response.json({ detail: "Backend chưa chạy trên cổng 8123" }, { status: 503 });
  }
}
