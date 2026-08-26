import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

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

/**
 * Paths que retornam streams binários (CSV, etc.) e NÃO devem ser bufferizados.
 * O proxy faz pipe direto do response.body sem chamar response.json().
 */
const STREAM_PATHS = [
	"api/v1/participants/export",
	"api/v2/participants/export",
];

function isStreamPath(path: string): boolean {
	return STREAM_PATHS.some((p) => path === p || path.startsWith(p + "?"));
}

/**
 * Lê os tokens de autenticação dos cookies httpOnly.
 *
 * - id_token: usado como `Authorization` para autenticar no backend (o
 *   backend extrai o CPF de `preferred_username` — claim que o access token
 *   do Keycloak pode não carregar).
 * - access_token: enviado em `X-Access-Token` para o backend repassar ao
 *   data-proxy (PostgREST), que seleciona a role pelo claim `$.role`
 *   (presente apenas no access token) e aplica RLS por `preferred_username`.
 */
function getAuthTokens(cookieStore: Awaited<ReturnType<typeof cookies>>) {
	return {
		idToken: cookieStore.get("id_token")?.value,
		accessToken: cookieStore.get("access_token")?.value,
	};
}

/**
 * Monta os headers de autenticação do backend: `Authorization` sempre com o
 * id token (fallback: access token, para sessões antigas) e, quando existir,
 * `X-Access-Token` com o access token para as chamadas ao data-proxy.
 */
function buildAuthHeaders(
	cookieStore: Awaited<ReturnType<typeof cookies>>,
): Record<string, string> {
	const { idToken, accessToken } = getAuthTokens(cookieStore);
	const token = idToken || accessToken;
	const headers: Record<string, string> = token
		? { Authorization: `Bearer ${token}` }
		: {};
	if (accessToken) {
		headers["X-Access-Token"] = accessToken;
	}
	return headers;
}

export async function GET(
	request: NextRequest,
	context: { params: Promise<{ path: string[] }> },
) {
	const cookieStore = await cookies();
	const headers = buildAuthHeaders(cookieStore);

	if (!headers.Authorization) {
		return NextResponse.json(
			{ error: "Unauthorized - No valid token" },
			{ status: 401 },
		);
	}

	const params = await context.params;
	const path = params.path.join("/");
	const searchParams = request.nextUrl.searchParams.toString();
	const targetUrl = `${API_URL}/${path}${searchParams ? `?${searchParams}` : ""}`;

	// --- Streaming path: pipe do body sem bufferizar ---
	if (isStreamPath(path)) {
		try {
			const response = await fetch(targetUrl, {
				method: "GET",
				headers,
				cache: "no-store",
				// @ts-expect-error — Node 18+ fetch suporta duplex mas os tipos não declaram
				duplex: "half",
			});

			if (!response.ok) {
				return NextResponse.json(
					{ error: `Backend returned ${response.status}` },
					{ status: response.status },
				);
			}

			// Repassar cabeçalhos relevantes do backend
			const responseHeaders = new Headers();
			const contentType = response.headers.get("content-type");
			const contentDisposition = response.headers.get("content-disposition");
			const xTotalRows = response.headers.get("x-total-rows");

			if (contentType) responseHeaders.set("content-type", contentType);
			if (contentDisposition)
				responseHeaders.set("content-disposition", contentDisposition);
			if (xTotalRows) responseHeaders.set("x-total-rows", xTotalRows);
			responseHeaders.set("cache-control", "no-store");
			responseHeaders.set("x-content-type-options", "nosniff");

			// Pipe do ReadableStream — o browser começa a receber bytes imediatamente
			return new Response(response.body, {
				status: response.status,
				headers: responseHeaders,
			});
		} catch (error) {
			console.error(`[Proxy GET Stream] Error:`, error);
			const isConnectionError =
				error instanceof TypeError && error.message === "fetch failed";
			return NextResponse.json(
				{
					error: isConnectionError
						? "Backend API unavailable"
						: "Failed to stream from backend API",
				},
				{ status: isConnectionError ? 503 : 500 },
			);
		}
	}

	// --- Caminho padrão: JSON bufferizado ---
	try {
		const response = await fetch(targetUrl, {
			method: "GET",
			headers,
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
		const isConnectionError =
			error instanceof TypeError && error.message === "fetch failed";
		return NextResponse.json(
			{
				error: isConnectionError
					? "Backend API unavailable"
					: "Failed to fetch from backend API",
			},
			{ status: isConnectionError ? 503 : 500 },
		);
	}
}

export async function POST(
	request: NextRequest,
	context: { params: Promise<{ path: string[] }> },
) {
	const cookieStore = await cookies();
	const headers = buildAuthHeaders(cookieStore);

	if (!headers.Authorization) {
		return NextResponse.json(
			{ error: "Unauthorized - No valid token" },
			{ status: 401 },
		);
	}

	const params = await context.params;
	const path = params.path.join("/");
	const targetUrl = `${API_URL}/${path}`;

	// Check if this is a file upload (multipart/form-data)
	const contentType = request.headers.get("content-type") || "";
	const isMultipart = contentType.includes("multipart/form-data");

	try {
		let response: Response;

		if (isMultipart) {
			// Handle file upload - forward the FormData as-is
			const formData = await request.formData();

			response = await fetch(targetUrl, {
				method: "POST",
				headers,
				// Don't set Content-Type for multipart - fetch will set it with boundary
				body: formData,
				cache: "no-store",
			});
		} else {
			// Handle JSON request
			const body = await request.json();

			response = await fetch(targetUrl, {
				method: "POST",
				headers: {
					...headers,
					"Content-Type": "application/json",
				},
				body: JSON.stringify(body),
				cache: "no-store",
			});
		}

		const data = await response.json();

		return NextResponse.json(data, {
			status: response.status,
		});
	} catch (error) {
		console.error(`[Proxy POST] Error:`, error);
		const isConnectionError =
			error instanceof TypeError && error.message === "fetch failed";
		return NextResponse.json(
			{
				error: isConnectionError
					? "Backend API unavailable"
					: "Failed to fetch from backend API",
			},
			{ status: isConnectionError ? 503 : 500 },
		);
	}
}

export async function PUT(
	request: NextRequest,
	context: { params: Promise<{ path: string[] }> },
) {
	const cookieStore = await cookies();
	const headers = buildAuthHeaders(cookieStore);

	if (!headers.Authorization) {
		return NextResponse.json(
			{ error: "Unauthorized - No valid token" },
			{ status: 401 },
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
				...headers,
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
		const isConnectionError =
			error instanceof TypeError && error.message === "fetch failed";
		return NextResponse.json(
			{
				error: isConnectionError
					? "Backend API unavailable"
					: "Failed to fetch from backend API",
			},
			{ status: isConnectionError ? 503 : 500 },
		);
	}
}

export async function DELETE(
	_request: NextRequest,
	context: { params: Promise<{ path: string[] }> },
) {
	const cookieStore = await cookies();
	const headers = buildAuthHeaders(cookieStore);

	if (!headers.Authorization) {
		return NextResponse.json(
			{ error: "Unauthorized - No valid token" },
			{ status: 401 },
		);
	}

	const params = await context.params;
	const path = params.path.join("/");
	const targetUrl = `${API_URL}/${path}`;

	try {
		const response = await fetch(targetUrl, {
			method: "DELETE",
			headers,
			cache: "no-store",
		});

		// 204 No Content não tem body
		if (response.status === 204) {
			return new NextResponse(null, {
				status: 204,
			});
		}

		const data = await response.json();

		return NextResponse.json(data, {
			status: response.status,
		});
	} catch (error) {
		console.error(`[Proxy DELETE] Error:`, error);
		const isConnectionError =
			error instanceof TypeError && error.message === "fetch failed";
		return NextResponse.json(
			{
				error: isConnectionError
					? "Backend API unavailable"
					: "Failed to fetch from backend API",
			},
			{ status: isConnectionError ? 503 : 500 },
		);
	}
}
