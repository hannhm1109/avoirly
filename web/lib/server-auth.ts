import "server-only";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { serverConfig } from "./server-config";

export async function authClient() {
  const config = serverConfig();
  if (!config.hosted) throw new Error("Hosted authentication is disabled.");
  const jar = await cookies();
  return createServerClient(config.supabase, config.publishable, {
    cookieOptions: { httpOnly: true, secure: true, sameSite: "lax", path: "/" },
    cookies: {
      getAll: () => jar.getAll(),
      setAll(values) {
        for (const { name, value, options } of values)
          jar.set(name, value, {
            ...options,
            httpOnly: true,
            secure: true,
            sameSite: "lax",
            path: "/",
            maxAge: options.maxAge === 0 ? 0 : 60 * 60 * 24 * 7,
          });
      },
    },
  });
}

export async function boundedBody(request: Request, max = 11 * 1024 * 1024) {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) {
      await reader.cancel();
      throw new Error("BODY_TOO_LARGE");
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.length;
  }
  return body;
}
