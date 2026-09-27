import { NextRequest, NextResponse } from "next/server";
export function proxy(request: NextRequest) {
  const host = request.headers.get("host") || "";
  if (!/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host))
    return new NextResponse("Local only", { status: 403 });
  const origin = request.headers.get("origin");
  if (origin && origin !== `http://${host}`)
    return new NextResponse("Origin forbidden", { status: 403 });
  return NextResponse.next();
}
export const config = { matcher: ["/api/:path*"] };
