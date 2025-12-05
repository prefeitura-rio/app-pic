import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Logout Handler
 *
 * Logs out from Keycloak and clears local session cookies.
 * Based on the working implementation from superapp.
 */
export async function GET() {
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get("refresh_token")?.value;

  // Logout from Keycloak if we have a refresh token
  if (refreshToken) {
    const logoutUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/logout`;
    const clientId = process.env.RMI_CLIENT_ID;
    const clientSecret = process.env.RMI_CLIENT_SECRET;

    if (clientId && clientSecret) {
      const params = new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
      });

      try {
        console.log("[Logout] Logging out from Keycloak");
        await fetch(logoutUrl, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: params,
        });
        console.log("[Logout] Keycloak logout successful");
      } catch (e) {
        console.error("[Logout] Error logging out from Keycloak:", e);
      }
    }
  }

  // Create response and clear all auth cookies
  const response = NextResponse.json({ success: true }, { status: 200 });

  response.cookies.set("access_token", "", {
    path: "/",
    httpOnly: true,
    maxAge: 0,
  });

  response.cookies.set("refresh_token", "", {
    path: "/",
    httpOnly: true,
    maxAge: 0,
  });

  response.cookies.set("id_token", "", {
    path: "/",
    httpOnly: true,
    maxAge: 0,
  });

  console.log("[Logout] Cookies cleared");

  return response;
}
