import {
  PaginatedResponse,
  Participante,
  ProtocoloDetalhes,
  SmartFilterOptions,
  DashboardFilters,
  ParticipantFilters,
} from "../types";

// Use server-side proxy to access backend API
// This allows reading API_URL from runtime environment (Infisical)
const BASE_URL = "/api/proxy";

/**
 * Attempt to refresh the access token using the refresh token
 */
async function tryRefreshToken(): Promise<boolean> {
  try {
    console.log("[API] Attempting token refresh...");
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
    });

    if (response.ok) {
      console.log("[API] Token refresh successful");
      return true;
    }

    console.warn("[API] Token refresh failed");
    return false;
  } catch (error) {
    console.error("[API] Token refresh error:", error);
    return false;
  }
}

/**
 * Handle API response with automatic token refresh on 401
 */
async function handleResponse<T>(
  response: Response,
  retryFn?: () => Promise<Response>
): Promise<T> {
  if (response.status === 401) {
    // Token expired - try to refresh
    console.warn("[API] Received 401, attempting token refresh...");

    const refreshed = await tryRefreshToken();

    if (refreshed && retryFn) {
      // Token refreshed successfully - retry the original request
      console.log("[API] Retrying original request after token refresh");
      const retryResponse = await retryFn();
      return handleResponse<T>(retryResponse); // Recursive call without retry to avoid infinite loop
    }

    // Refresh failed or no retry function - redirect to login
    console.warn("[API] Token refresh failed. Redirecting to login...");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }

  return response.json();
}

/**
 * Build query parameters from filter object, excluding default "todos"/"todas" values
 */
function buildFilterParams(
  filters: DashboardFilters | ParticipantFilters
): URLSearchParams {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value && value !== "todos" && value !== "todas" && value !== "") {
      params.append(key, value);
    }
  });

  return params;
}

/**
 * Main API service - agora todos os endpoints retornam filtros dinâmicos na resposta
 */
export const apiService = {

  /**
   * Get dashboard metrics with filters.
   *
   * @param filters - Filter criteria
   * @returns Dashboard data
   */
  async getDashboard(
    filters: DashboardFilters = {}
  ): Promise<PaginatedResponse<any>> {
    const params = buildFilterParams(filters);
    const url = `${BASE_URL}/api/v1/dashboard/?${params.toString()}`;

    console.log("[API] getDashboard - Filters:", filters);
    console.log("[API] getDashboard - URL:", url);

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<PaginatedResponse<any>>(res, fetchFn);
  },

  /**
   * Get participants with filters and pagination.
   * Used by both Overview tab (for calculations) and Professional tab (for table display).
   *
   * @param filters - Filter criteria (bairro, cre, cras, escola, clinica, safra, grupo, status)
   * @param page - Page number (1-indexed)
   * @param pageSize - Items per page
   * @returns Paginated response with participants
   */
  async getParticipants(
    filters: ParticipantFilters = {},
    page: number = 1,
    pageSize: number = 100
  ): Promise<PaginatedResponse<Participante>> {
    const params = buildFilterParams(filters);
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());

    const url = `${BASE_URL}/api/v1/participants/?${params.toString()}`;

    console.log("[API] getParticipants - Filters:", filters);
    console.log("[API] getParticipants - Page:", page, "PageSize:", pageSize);
    console.log("[API] getParticipants - URL:", url);

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<PaginatedResponse<Participante>>(res, fetchFn);
  },

  /**
   * Get details for a specific participant by CPF.
   *
   * @param cpf - Participant CPF
   * @returns Participant details
   */
  async getParticipantDetails(
    cpf: string
  ): Promise<Participante> {
    const url = `${BASE_URL}/api/v1/participants/${cpf}`;

    console.log("[API] getParticipantDetails - CPF:", cpf);
    console.log("[API] getParticipantDetails - URL:", url);

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    const response = await handleResponse<PaginatedResponse<Participante>>(res, fetchFn);

    if (response.data && response.data.length > 0) {
      return response.data[0];
    }

    throw new Error("Participant not found");
  },

  /**
   * Get protocols for a specific participant by CPF.
   *
   * @param cpf - Participant CPF
   * @returns List of protocol details
   */
  async getParticipantProtocols(
    cpf: string
  ): Promise<ProtocoloDetalhes[]> {
    const url = `${BASE_URL}/api/v1/participants/${cpf}/protocols`;

    console.log("[API] getParticipantProtocols - CPF:", cpf);
    console.log("[API] getParticipantProtocols - URL:", url);

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    const response = await handleResponse<PaginatedResponse<ProtocoloDetalhes>>(
      res,
      fetchFn
    );

    return response.data || [];
  },
};
