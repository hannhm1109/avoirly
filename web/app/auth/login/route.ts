import { authClient, boundedBody } from "@/lib/server-auth";
export async function POST(request: Request) {
  try {
    const input = JSON.parse(
      new TextDecoder().decode(await boundedBody(request, 8192)),
    );
    if (
      typeof input.email !== "string" ||
      typeof input.password !== "string" ||
      input.email.length > 320 ||
      input.password.length > 1024
    )
      return Response.json(
        { error: "Identifiants invalides." },
        { status: 400 },
      );
    const client = await authClient();
    const { error } = await client.auth.signInWithPassword({
      email: input.email,
      password: input.password,
    });
    return Response.json(
      error
        ? {
            error:
              "Connexion impossible. Vérifiez vos identifiants ou réessayez plus tard.",
          }
        : { ok: true },
      { status: error ? 401 : 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      { error: "Connexion temporairement indisponible." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
