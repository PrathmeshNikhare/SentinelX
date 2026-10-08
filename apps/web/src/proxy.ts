import { NextResponse, type NextRequest } from "next/server";

// Optimistic auth boundary (D-034): only checks that a session cookie exists. Pages and API routes
// validate the session against PostgreSQL themselves; API routes answer 401 JSON instead of redirecting.
const SESSION_COOKIE = "sx_session";

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/api/") || pathname === "/login") return NextResponse.next();
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
