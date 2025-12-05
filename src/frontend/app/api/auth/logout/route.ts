import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Logout Handler
 *
 * Clears local session cookies and redirects to Keycloak logout endpoint.
 * This ensures both local session AND Keycloak SSO session (including GovBR) are cleared.
 */
export async function GET() {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const refreshToken = cookieStore.get("refresh_token")?.value;

  // Strategy 1: If we have refresh_token, call logout endpoint server-side first
  if (refreshToken) {
    const logoutUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/logout`;
    const params = new URLSearchParams({
      client_id: process.env.RMI_CLIENT_ID!,
      client_secret: process.env.RMI_CLIENT_SECRET!,
      refresh_token: refreshToken,
    });

    try {
      console.log("[Logout] Calling Keycloak logout endpoint with refresh_token");
      await fetch(logoutUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params,
      });
    } catch (e) {
      console.error("[Logout] Error calling logout endpoint:", e);
    }
  }

  // Strategy 2: Redirect browser to logout URL to clear SSO session
  const keycloakLogoutUrl = `${process.env.RMI_ISSUER}/protocol/openid-connect/logout`;
  const postLogoutRedirectUri = `${process.env.NEXTAUTH_URL}/login`;

  const urlParams = new URLSearchParams({
    post_logout_redirect_uri: postLogoutRedirectUri,
  });

  // Add id_token_hint if available (recommended by OIDC spec)
  if (idToken) {
    urlParams.append("id_token_hint", idToken);
  }

  const logoutRedirectUrl = `${keycloakLogoutUrl}?${urlParams.toString()}`;

  // Create redirect response
  const response = NextResponse.redirect(logoutRedirectUrl);

  // Clear all auth cookies before redirecting
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

  console.log("[Logout] Redirecting browser to Keycloak logout:", logoutRedirectUrl);

  return response;
}
