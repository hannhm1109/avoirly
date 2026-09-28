import { authClient } from "@/lib/server-auth";
export async function POST() {
  try {
    const client = await authClient();
    const { error } = await client.auth.signOut({ scope: "local" });
    return Response.json(
      { ok: !error },
      { status: error ? 503 : 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json({ ok: false }, { status: 503 });
  }
}
