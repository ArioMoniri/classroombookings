import { NextResponse, type NextRequest } from "next/server";
import { stripCredentialParams } from "@/components/auth/credential-form";

/**
 * HB18-F02: where a credential form posts when it is submitted natively (before hydration, or with scripts off). It
 * never reads the body (the password) and answers 303 back to the same-origin page it came from (the Referer), minus
 * any credential parameter; anything else (another origin, the API, no Referer) goes to /login.
 */
function back(request: NextRequest): NextResponse {
  let location = "/login";
  const ref = request.headers.get("referer");
  if (ref) {
    try {
      const url = new URL(ref);
      if (url.origin === request.nextUrl.origin && !url.pathname.startsWith("/api/") && !url.pathname.startsWith("//")) {
        const search = stripCredentialParams(url.searchParams) ?? url.searchParams;
        const q = search.toString();
        location = `${url.pathname}${q ? `?${q}` : ""}`;
      }
    } catch {
      // an unreadable Referer: /login
    }
  }
  return new NextResponse(null, { status: 303, headers: { location, "cache-control": "no-store", "referrer-policy": "no-referrer" } });
}

export function POST(request: NextRequest): NextResponse {
  return back(request);
}

export function GET(request: NextRequest): NextResponse {
  return back(request);
}
