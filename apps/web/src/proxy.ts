import { NextResponse, type NextRequest } from "next/server";

// Send visitors without a language prefix to /en or /fr, from their browser preference.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const preferred = request.headers.get("accept-language") ?? "";
  const lang = /^\s*fr\b/i.test(preferred) || /,\s*fr\b(?!.*\ben\b)/i.test(preferred) ? "fr" : "en";
  request.nextUrl.pathname = `/${lang}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(request.nextUrl);
}

export const config = {
  // Everything except locale-prefixed pages, the console, Next internals and static files.
  matcher: ["/((?!en(?:/|$)|fr(?:/|$)|console|_next|favicon\\.ico|.*\\.).*)"],
};
