import createIntlMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

/**
 * The single request proxy (Next 16: one proxy file per project).
 *
 * 1. Basic Auth on every page and API call (BASIC_AUTH_USERS = "user:password,..."). Not configured:
 *    503, never open by mistake.
 * 2. API calls proxied to the backend (next.config rewrites /api/*) carry the internal token and the
 *    authenticated user: the backend requires the token on every write route and records this user as
 *    the actor of a decision. Both headers are set here only, never trusted from the browser.
 * 3. Pages: locale prefix (next-intl), "/" -> "/fr".
 */
const intl = createIntlMiddleware(routing);

function authenticatedUser(req: NextRequest, users: string[]): string | null {
  const header = req.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) return null;
  try {
    const credentials = atob(header.slice(6));
    return users.includes(credentials) ? credentials.split(":")[0] : null;
  } catch {
    return null;
  }
}

export function proxy(req: NextRequest) {
  const users = (process.env.BASIC_AUTH_USERS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const french = req.nextUrl.pathname.startsWith("/fr") || req.nextUrl.pathname === "/";
  if (users.length === 0) {
    return new NextResponse(french ? "Authentification non configurée" : "Authentication not configured", {
      status: 503,
    });
  }
  const user = authenticatedUser(req, users);
  if (!user) {
    return new NextResponse(french ? "Authentification requise" : "Authentication required", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="UMOA", charset="UTF-8"' },
    });
  }

  if (req.nextUrl.pathname.startsWith("/api/")) {
    const headers = new Headers(req.headers);
    headers.delete("x-internal-token");
    headers.set("x-authenticated-user", user);
    if (process.env.INTERNAL_API_TOKEN) headers.set("x-internal-token", process.env.INTERNAL_API_TOKEN);
    return NextResponse.next({ request: { headers } });
  }
  return intl(req);
}

export const config = {
  // Everything but Next internals and static files (a path with an extension).
  matcher: ["/((?!_next|_vercel|.*\\..*).*)"],
};
