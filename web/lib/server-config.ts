import "server-only";
export function serverConfig() {
  const mode = process.env.AVOIRLY_MODE || "local";
  if (!["local", "hosted"].includes(mode))
    throw new Error("Select local or hosted mode.");
  const hosted = mode === "hosted";
  const api = new URL(
    process.env.AVOIRLY_API_ORIGIN || "http://127.0.0.1:8000",
  );
  const web = new URL(
    process.env.AVOIRLY_WEB_ORIGIN || "http://127.0.0.1:3000",
  );
  for (const url of [api, web]) {
    if (
      url.pathname !== "/" ||
      url.search ||
      url.hash ||
      url.username ||
      url.password
    )
      throw new Error("Origins must not contain paths or credentials.");
    if (
      hosted
        ? url.protocol !== "https:"
        : url.protocol !== "http:" ||
          !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
    )
      throw new Error("Invalid application origin.");
  }
  const supabase = process.env.SUPABASE_URL || "";
  const publishable = process.env.SUPABASE_PUBLISHABLE_KEY || "";
  if (
    hosted &&
    (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(supabase) ||
      !publishable.startsWith("sb_publishable_"))
  )
    throw new Error("Configure Supabase server-side auth.");
  return { hosted, api: api.origin, web: web.origin, supabase, publishable };
}
