import { NextRequest, NextResponse } from "next/server";
import { serverConfig } from "./lib/server-config";
export function proxy(request: NextRequest) {
  let settings;
  try {
    settings = serverConfig();
  } catch {
    return NextResponse.json(
      { code: "CONFIGURATION_REQUIRED" },
      { status: 503 },
    );
  }
  const host = request.headers.get("host") || "";
  if (
    settings.hosted
      ? host !== new URL(settings.web).host
      : !/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host)
  )
    return new NextResponse("Local only", { status: 403 });
  const origin = request.headers.get("origin");
  if (
    (origin &&
      origin !== (settings.hosted ? settings.web : `http://${host}`)) ||
    (settings.hosted &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method) &&
      !origin)
  )
    return new NextResponse("Origin forbidden", { status: 403 });
  if (request.headers.get("sec-fetch-site") === "cross-site")
    return new NextResponse("Cross-site request forbidden", { status: 403 });
  return NextResponse.next();
}
export const config = { matcher: ["/api/:path*", "/auth/:path*"] };
