import { getSessionToken } from "@/lib/auth";

function apiBase(): string {
  return (
    process.env.AEIOS_API_URL ||
    process.env.NEXT_PUBLIC_AEIOS_API_URL ||
    "http://127.0.0.1:8080"
  ).replace(/\/$/, "");
}

/** Proxies FastAPI SSE so the browser can stream without exposing API tokens. */
export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const token = await getSessionToken();
  if (!token) {
    return new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const upstream = await fetch(`${apiBase()}/v1/tasks/${encodeURIComponent(id)}/events`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text || JSON.stringify({ detail: "Upstream SSE failed" }), {
      status: upstream.status || 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
