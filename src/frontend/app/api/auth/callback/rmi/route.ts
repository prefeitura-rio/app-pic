import { NextRequest, NextResponse } from "next/server";

/**
 * OAuth2 Callback Handler for Keycloak/RMI
 *
 * This endpoint receives the authorization code from Keycloak and exchanges it for tokens.
 * Based on the working implementation from superapp.
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const code = searchParams.get("code");
    const state = searchParams.get("state"); // Contains the return URL

    if (!code) {
      console.error("[OAuth Callback] No authorization code received");
      return NextResponse.redirect(new URL("/login", req.url));
    }

    // Exchange authorization code for tokens
    const tokenUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/token`;
    const params = new URLSearchParams({
      client_id: process.env.RMI_CLIENT_ID!,
      client_secret: process.env.RMI_CLIENT_SECRET!,
      grant_type: "authorization_code",
      code,
      redirect_uri: `${process.env.NEXTAUTH_URL}/api/auth/callback/rmi`,
    });

    console.log(`[OAuth Callback] Exchanging code for tokens at ${tokenUrl}`);

    const response = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params,
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("[OAuth Callback] Token exchange failed:", error);
      return NextResponse.redirect(new URL("/login", req.url));
    }

    const data = await response.json();

    console.log("[OAuth Callback] Token exchange successful");
    console.log("[OAuth Callback] Tokens received:", {
      has_access_token: !!data.access_token,
      has_refresh_token: !!data.refresh_token,
      has_id_token: !!data.id_token,
      expires_in: data.expires_in,
      refresh_expires_in: data.refresh_expires_in,
    });

    // Determine redirect destination
    let finalRedirectUrl = "/";
    if (state) {
      try {
        const decodedState = decodeURIComponent(state);
        if (decodedState.startsWith("/") && !decodedState.startsWith("//")) {
          finalRedirectUrl = decodedState;
        }
      } catch (e) {
        console.error("[OAuth Callback] Error decoding state:", e);
      }
    }

    // Create response with redirect
    const res = NextResponse.redirect(new URL(finalRedirectUrl, req.url));

    // Store tokens in httpOnly cookies for security
    res.cookies.set("access_token", data.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: data.expires_in || 3600, // Default 1 hour
    });

    if (data.refresh_token) {
      res.cookies.set("refresh_token", data.refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: data.refresh_expires_in || 86400, // Default 24 hours
      });
    }

    if (data.id_token) {
      res.cookies.set("id_token", data.id_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: data.expires_in || 3600,
      });
    }

    return res;
  } catch (error) {
    console.error("[OAuth Callback] Unexpected error:", error);
    return NextResponse.redirect(new URL("/login", req.url));
  }
}
