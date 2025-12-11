import {
  PaginatedResponse,
  Participante,
  ProtocoloDetalhes,
  SmartFilterOptions,
  ParticipantFilters,
  AvailableIds,
  UserAccessRecord,
  CreateUserRequest,
} from "../types";
import { DashboardFilterValues } from "../components/DashboardFilterCard";

// Use server-side proxy to access backend API
// This allows reading API_URL from runtime environment (Infisical)
const BASE_URL = "/api/proxy";

/**
 * Attempt to refresh the access token using the refresh token
 */
async function tryRefreshToken(): Promise<boolean> {
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
    });

    if (response.ok) {
      return true;
    }

    return false;
  } catch (error) {
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

    const refreshed = await tryRefreshToken();

    if (refreshed && retryFn) {
      // Token refreshed successfully - retry the original request
      const retryResponse = await retryFn();
      return handleResponse<T>(retryResponse); // Recursive call without retry to avoid infinite loop
    }

    // Refresh failed or no retry function - redirect to login
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  // Handle Forbidden (403) - User logged in but no permission
  if (response.status === 403) {
    const errorData = await response.json();
    const detail = errorData.detail || JSON.stringify(errorData);
    const detailStr = String(detail).toLowerCase();

    // Persistir log no localStorage para debug
    localStorage.setItem('last_403_error', JSON.stringify({
      detail: detail,
      detailStr: detailStr,
      timestamp: new Date().toISOString()
    }));

    // 1. Check for inactive user
    if (detailStr.includes("inativo")) {
      window.location.href = "/login?error=InactiveUser";
      throw new Error("User Inactive");
    }

    // 2. Check for non-admin trying to access admin endpoints
    if (detailStr.includes("apenas admins podem") || detailStr.includes("apenas admins") || detailStr.includes("admin")) {
      // Importar toast dinamicamente
      import('sonner').then(({ toast }) => {
        toast.error('Acesso Negado', {
          description: 'Você não possui permissões de administrador. Apenas administradores podem acessar esta área.',
          duration: 6000,
        });
      });
      throw new Error("Not Admin");
    }

    // 3. CPF não cadastrado ou outro erro de acesso
    const safeDetail = encodeURIComponent(detailStr.substring(0, 200));
    window.location.href = `/login?error=AccessDenied&details=${safeDetail}`;
    throw new Error(`Access Denied: ${detail}`);
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
  filters: DashboardFilterValues | ParticipantFilters
): URLSearchParams {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    // Skip empty values and defaults
    if (value === null || value === undefined || value === "" || value === "todos" || value === "todas") {
      return;
    }

    // Convert boolean to string explicitly
    if (typeof value === "boolean") {
      params.append(key, value.toString());
    } else if (value) {
      params.append(key, value.toString());
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
    filters: DashboardFilterValues = {}
  ): Promise<PaginatedResponse<any>> {
    const params = buildFilterParams(filters);
    const url = `${BASE_URL}/api/v1/dashboard?${params.toString()}`;

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

    const url = `${BASE_URL}/api/v1/participants?${params.toString()}`;

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

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    const response = await handleResponse<PaginatedResponse<ProtocoloDetalhes>>(
      res,
      fetchFn
    );

    return response.data || [];
  },

  // ========================================================================
  // ADMIN ENDPOINTS
  // ========================================================================

  /**
   * Get all available IDs for assignment (CRAS, schools, CRE, etc)
   * Requires admin permission
   *
   * @returns Available IDs grouped by type
   */
  async getCurrentUser(): Promise<UserAccessRecord> {
    const url = `${BASE_URL}/api/v1/admin/me`;

    const fetchFn = () => fetch(url);
    const res = await fetchFn();

    return handleResponse<UserAccessRecord>(res, fetchFn);
  },

  async getAvailableIds(): Promise<AvailableIds> {
    const url = `${BASE_URL}/api/v1/admin/available-ids`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<AvailableIds>(res, fetchFn);
  },

  /**
   * Get list of users the admin can manage (with pagination)
   * Requires admin permission
   *
   * @param page - Page number (1-indexed)
   * @param pageSize - Items per page
   * @param activeOnly - Filter only active users (true/false/null for all)
   * @param search - Search by CPF or name
   * @returns Paginated response with user access records
   */
  async getUsers(
    page: number = 1,
    pageSize: number = 100,
    activeOnly?: boolean,
    search?: string
  ): Promise<PaginatedResponse<UserAccessRecord>> {
    const params = new URLSearchParams();
    
    // Defensive programming: ensure page is a number
    // This handles cases where page might be passed as "true" or boolean by mistake
    const pageNum = typeof page === 'number' ? page : 1;
    
    params.append("page", pageNum.toString());
    params.append("page_size", pageSize.toString());

    if (activeOnly !== undefined) {
      params.append("active_only", activeOnly.toString());
    }

    if (search) {
      params.append("search", search);
    }

    const url = `${BASE_URL}/api/v1/admin/users?${params.toString()}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<PaginatedResponse<UserAccessRecord>>(res, fetchFn);
  },

  /**
   * Create or update a user (UPSERT)
   * Requires admin permission
   *
   * If CPF exists: updates permissions
   * If CPF doesn't exist: creates new user
   *
   * @param cpf - User CPF (11 digits)
   * @param userData - User data
   * @returns User record
   */
  async upsertUser(
    cpf: string,
    userData: Omit<CreateUserRequest, "cpf">
  ): Promise<UserAccessRecord> {
    const url = `${BASE_URL}/api/v1/admin/users/${cpf}`;

    const fetchFn = () =>
      fetch(url, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(userData),
      });

    const res = await fetchFn();

    return handleResponse<UserAccessRecord>(res, fetchFn);
  },


  /**
   * Delete (soft-delete) a user
   * Requires admin permission
   *
   * @param cpf - User CPF
   */
  async deleteUser(cpf: string): Promise<void> {
    const url = `${BASE_URL}/api/v1/admin/users/${cpf}`;

    const fetchFn = () =>
      fetch(url, {
        method: "DELETE",
      });

    const res = await fetchFn();

    if (res.status === 204) {
      return; // Success - no content
    }

    // Handle other responses
    await handleResponse<void>(res, fetchFn);
  },
};
