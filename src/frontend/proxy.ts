import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isJwtExpired } from "@/app/utils/jwt-utils";

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public routes
  if (pathname === "/login" || pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  // Check for access token
  const accessToken = request.cookies.get("access_token")?.value;

  // If no token, redirect to login
  if (!accessToken) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  // Check if token is expired
  if (isJwtExpired(accessToken)) {
    // Token expired - redirect to login
    // In the future, we can implement automatic refresh here
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  // Token is valid, allow access
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
