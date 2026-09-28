import { authClient, boundedBody } from "@/lib/server-auth";
import { serverConfig } from "@/lib/server-config";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
type Context = { params: Promise<{ path: string[] }> };
async function forward(request: Request, context: Context) {
  try {
    const config = serverConfig();
    const { path } = await context.params;
    if (!path.length || path.some((p) => !/^[a-zA-Z0-9-]+$/.test(p)))
      return Response.json({ code: "NOT_FOUND" }, { status: 404 });
    const headers = new Headers();
    if (config.hosted) {
      const client = await authClient();
      const { data, error } = await client.auth.getSession();
      if (error || !data.session)
        return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
      headers.set("Authorization", `Bearer ${data.session.access_token}`);
    }
    for (const name of ["content-type", "idempotency-key"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    // Never forward client identity, cookies, arbitrary hosts, or operator credentials.
    const url = new URL(`${config.api}/api/v1/${path.join("/")}`);
    url.search = new URL(request.url).search;
    const body = ["GET", "HEAD"].includes(request.method)
      ? undefined
      : await boundedBody(request);
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(60000),
    });
    const resultHeaders = new Headers({
      "Cache-Control": "private, no-store",
      Vary: "Cookie",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of [
      "content-type",
      "content-disposition",
      "content-security-policy",
      "x-request-id",
    ]) {
      const value = upstream.headers.get(name);
      if (value) resultHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: resultHeaders,
    });
  } catch (error) {
    const large = error instanceof Error && error.message === "BODY_TOO_LARGE";
    return Response.json(
      { code: large ? "FILE_SIZE" : "SERVER_UNAVAILABLE" },
      { status: large ? 413 : 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
