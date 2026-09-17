import createMiddleware from "next-intl/middleware";
import { routing } from "./src/i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Match all pathnames except:
  // - API routes
  // - Next.js internals (_next)
  // - Static files (public directory)
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
