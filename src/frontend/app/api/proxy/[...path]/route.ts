import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

/**
 * Backend API Proxy - Server-Side Requests
 *
 * All API requests go through this proxy to:
 * 1. Keep API URL configuration on the server (reads from Infisical at runtime)
 * 2. Add authentication token automatically
 * 3. Avoid CORS issues
 * 4. Keep internal K8s URLs private
 *
 * Flow:
 * - Client calls: /api/proxy/api/v1/dashboard
 * - Proxy forwards to: ${API_URL}/api/v1/dashboard (internal K8s URL)
 *
 * Environment Variables (from Infisical - runtime):
 * - API_URL: Backend API URL (e.g., http://api.app-pic-staging.svc.cluster.local)
 */

const API_URL = process.env.API_URL;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  // Use ID Token for authentication (Keycloak Access Token may be opaque)
  const token = idToken || accessToken;

  if (!token) {
    return NextResponse.json(
      { error: "Unauthorized - No valid token" },
      { status: 401 }
    );
  }

  const params = await context.params;
  const path = params.path.join("/");
  const searchParams = request.nextUrl.searchParams.toString();
  const targetUrl = `${API_URL}/${path}${searchParams ? `?${searchParams}` : ""}`;


  try {
    const response = await fetch(targetUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    const data = await response.json();

    return NextResponse.json(data, {
      status: response.status,
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error(`[Proxy GET] Error:`, error);
    return NextResponse.json(
      { error: "Failed to fetch from backend API" },
      { status: 500 }
    );
  }
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  const token = idToken || accessToken;

  if (!token) {
    return NextResponse.json(
      { error: "Unauthorized - No valid token" },
      { status: 401 }
    );
  }

  const params = await context.params;
  const path = params.path.join("/");
  const targetUrl = `${API_URL}/${path}`;
  const body = await request.json();


  try {
    const response = await fetch(targetUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    const data = await response.json();

    return NextResponse.json(data, {
      status: response.status,
    });
  } catch (error) {
    console.error(`[Proxy POST] Error:`, error);
    return NextResponse.json(
      { error: "Failed to fetch from backend API" },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  const token = idToken || accessToken;

  if (!token) {
    return NextResponse.json(
      { error: "Unauthorized - No valid token" },
      { status: 401 }
    );
  }

  const params = await context.params;
  const path = params.path.join("/");
  const targetUrl = `${API_URL}/${path}`;
  const body = await request.json();


  try {
    const response = await fetch(targetUrl, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    const data = await response.json();

    return NextResponse.json(data, {
      status: response.status,
    });
  } catch (error) {
    console.error(`[Proxy PUT] Error:`, error);
    return NextResponse.json(
      { error: "Failed to fetch from backend API" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const cookieStore = await cookies();
  const idToken = cookieStore.get("id_token")?.value;
  const accessToken = cookieStore.get("access_token")?.value;

  const token = idToken || accessToken;

  if (!token) {
    return NextResponse.json(
      { error: "Unauthorized - No valid token" },
      { status: 401 }
    );
  }

  const params = await context.params;
  const path = params.path.join("/");
  const targetUrl = `${API_URL}/${path}`;


  try {
    const response = await fetch(targetUrl, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    const data = await response.json();

    return NextResponse.json(data, {
      status: response.status,
    });
  } catch (error) {
    console.error(`[Proxy DELETE] Error:`, error);
    return NextResponse.json(
      { error: "Failed to fetch from backend API" },
      { status: 500 }
    );
  }
}
