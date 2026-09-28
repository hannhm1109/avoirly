import { authClient } from "@/lib/server-auth";
import { serverConfig } from "@/lib/server-config";
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const config = serverConfig();
    if (!config.hosted)
      return Response.json(
        { mode: "local", signed_in: true },
        { headers: { "Cache-Control": "no-store" } },
      );
    const client = await authClient();
    const { data, error } = await client.auth.getUser();
    return Response.json(
      {
        mode: "hosted",
        signed_in: !error && !!data.user,
        email: data.user?.email || null,
      },
      { headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } },
    );
  } catch {
    return Response.json(
      { mode: "hosted", signed_in: false },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
