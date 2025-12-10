import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Token Refresh Handler
 *
 * Uses the refresh_token to obtain new access_token and id_token.
 * This allows seamless session continuation without re-authentication.
 */
export async function POST() {
  try {
    const cookieStore = await cookies();
    const refreshToken = cookieStore.get("refresh_token")?.value;

    if (!refreshToken) {
      console.error("[Token Refresh] No refresh_token available");
      return NextResponse.json(
        { error: "No refresh token" },
        { status: 401 }
      );
    }

    // Exchange refresh_token for new tokens
    const tokenUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/token`;
    const params = new URLSearchParams({
      client_id: process.env.RMI_CLIENT_ID!,
      client_secret: process.env.RMI_CLIENT_SECRET!,
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    });


    const response = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params,
    });

    if (!response.ok) {
      const error = await response.text();
      console.error("[Token Refresh] Failed to refresh tokens:", error);
      return NextResponse.json(
        { error: "Token refresh failed" },
        { status: 401 }
      );
    }

    const data = await response.json();

    console.log("[Token Refresh] Token refresh successful");
    console.log("[Token Refresh] New tokens:", {
      has_access_token: !!data.access_token,
      has_refresh_token: !!data.refresh_token,
      has_id_token: !!data.id_token,
      expires_in: data.expires_in,
      refresh_expires_in: data.refresh_expires_in,
    });

    // Create response
    const res = NextResponse.json({ success: true }, { status: 200 });

    // Update cookies with new tokens
    res.cookies.set("access_token", data.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: data.expires_in || 3600,
    });

    if (data.refresh_token) {
      res.cookies.set("refresh_token", data.refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: data.refresh_expires_in || 1800,
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
    console.error("[Token Refresh] Unexpected error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
