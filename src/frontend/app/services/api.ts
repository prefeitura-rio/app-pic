/* eslint-disable @typescript-eslint/no-explicit-any */
import {
  PaginatedResponse,
  PaginatedResponseV2,
  Participante,
  ParticipanteListItem,
  ParticipantDetailResponse,
  DashboardV2Response,
  ProtocoloDetalhes,
  SmartFilterOptions,
  ParticipantFilters,
  AvailableIds,
  UserAccessRecord,
  CreateUserRequest,
  BatchImportResult,
  BatchPermissionsRequest,
  BatchPermissionsResult,
  GeospatialLayer,
  GeospatialLayersResponse,
  GeospatialFilterVocabularyResponse,
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
  } catch (_error) {
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

    // Handle arrays (multi-select filters)
    if (Array.isArray(value)) {
      // Skip empty arrays
      if (value.length === 0) {
        return;
      }
      // Send as pipe-separated string for the backend
      // NOTE: comma cannot be used as delimiter because some values (e.g. protocolo_descricao) contain commas
      params.append(key, value.join("|"));
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
   * V2 — Dashboard metrics without inline filters.
   */
  async getDashboardV2(
    filters: DashboardFilterValues = {}
  ): Promise<DashboardV2Response> {
    const params = buildFilterParams(filters);
    const url = `${BASE_URL}/api/v2/dashboard?${params.toString()}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<DashboardV2Response>(res, fetchFn);
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
   * V2 — Lista paginada enxuta (13 campos, sem protocolo_listagem, sem cascade).
   */
  async getParticipantsV2(
    filters: ParticipantFilters = {},
    page: number = 1,
    pageSize: number = 100
  ): Promise<PaginatedResponseV2<ParticipanteListItem>> {
    const params = buildFilterParams(filters);
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());

    const url = `${BASE_URL}/api/v2/participants?${params.toString()}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<PaginatedResponseV2<ParticipanteListItem>>(res, fetchFn);
  },

  /**
   * V2 — Detalhe completo de um participante por id_membro_familia.
   */
  async getParticipantDetailV2(
    idMembroFamilia: string
  ): Promise<ParticipantDetailResponse> {
    const url = `${BASE_URL}/api/v2/participants/${idMembroFamilia}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<ParticipantDetailResponse>(res, fetchFn);
  },

  /**
   * V2 — Vocabulário completo de opções de filtro (16 arrays).
   * Aceita filtros ativos para cascateamento contextual.
   */
  async getFilterVocabulary(activeFilters?: DashboardFilterValues | ParticipantFilters): Promise<SmartFilterOptions> {
    let url = `${BASE_URL}/api/v2/filters`;

    if (activeFilters) {
      const params = buildFilterParams(activeFilters);
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<SmartFilterOptions>(res, fetchFn);
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


  /**
   * Export all filtered participants as a streaming CSV download.
   *
   * Returns a Response with a ReadableStream body — the caller should
   * consume it via response.blob() or pipe it to the File System API.
   * No JSON parsing involved; the proxy pipes the CSV bytes directly.
   *
   * @param filters - Filter criteria (same as getParticipants)
   * @returns Raw fetch Response (streaming)
   */
  async exportParticipants(
    filters: ParticipantFilters = {}
  ): Promise<Response> {
    const params = buildFilterParams(filters);
    const url = `${BASE_URL}/api/v2/participants/export?${params.toString()}`;

    const response = await fetch(url, { cache: "no-store" });

    if (response.status === 401) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        const retry = await fetch(url, { cache: "no-store" });
        if (!retry.ok) {
          window.location.href = "/login";
          throw new Error("Unauthorized");
        }
        return retry;
      }
      window.location.href = "/login";
      throw new Error("Unauthorized");
    }

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Export Error ${response.status}: ${errorText}`);
    }

    return response;
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
    const url = `${BASE_URL}/api/v2/admin/me`;

    const fetchFn = () => fetch(url);
    const res = await fetchFn();

    return handleResponse<UserAccessRecord>(res, fetchFn);
  },

  async getAvailableIds(): Promise<AvailableIds> {
    const url = `${BASE_URL}/api/v2/admin/available-ids`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<AvailableIds>(res, fetchFn);
  },

  /**
   * Get list of users the admin can manage (with pagination)
   * Requires admin permission
   *
   * @param options - Filter and pagination options
   * @returns Paginated response with user access records
   */
  async getUsers(
    options: {
      page?: number;
      pageSize?: number;
      activeOnly?: boolean;
      search?: string;
      ocupacao?: string;
      secretaria?: string;
      permission?: string;
      secretariaAcesso?: string;
      bypassCache?: boolean;
    } = {}
  ): Promise<PaginatedResponse<UserAccessRecord>> {
    const params = new URLSearchParams();

    const pageNum = typeof options.page === 'number' ? options.page : 1;
    params.append("page", pageNum.toString());
    params.append("page_size", String(options.pageSize ?? 100));

    if (options.activeOnly !== undefined) {
      params.append("active", options.activeOnly.toString());
    }

    if (options.search) {
      params.append("search", options.search);
    }

    if (options.ocupacao) {
      params.append("ocupacao", options.ocupacao);
    }

    if (options.secretaria) {
      params.append("secretaria", options.secretaria);
    }

    if (options.permission) {
      params.append("permission", options.permission);
    }

    if (options.secretariaAcesso) {
      params.append("secretaria_acesso", options.secretariaAcesso);
    }

    if (options.bypassCache) {
      params.append("bypass_cache", "true");
    }

    const url = `${BASE_URL}/api/v2/admin/users?${params.toString()}`;

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
    const url = `${BASE_URL}/api/v2/admin/users/${cpf}`;

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
    const url = `${BASE_URL}/api/v2/admin/users/${cpf}`;

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

  // ========================================================================
  // BATCH IMPORT ENDPOINTS
  // ========================================================================

  /**
   * Import users in batch from CSV or XLSX file
   * Requires admin permission
   *
   * @param file - CSV or XLSX file
   * @returns Batch import result with list of processed users
   */
  async batchImportUsers(file: File): Promise<BatchImportResult> {
    const url = `${BASE_URL}/api/v2/admin/users-batch`;

    const formData = new FormData();
    formData.append("file", file);

    const fetchFn = () =>
      fetch(url, {
        method: "POST",
        body: formData,
      });

    const res = await fetchFn();

    return handleResponse<BatchImportResult>(res, fetchFn);
  },

  /**
   * Update permissions for multiple users in batch
   * Requires admin permission
   *
   * @param request - Batch permissions request
   * @returns Batch permissions result
   */
  async batchUpdatePermissions(
    request: BatchPermissionsRequest
  ): Promise<BatchPermissionsResult> {
    const url = `${BASE_URL}/api/v2/admin/users-batch/permissions`;

    const fetchFn = () =>
      fetch(url, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

    const res = await fetchFn();

    return handleResponse<BatchPermissionsResult>(res, fetchFn);
  },

  // ========================================================================
  // DEBUG ENDPOINTS (Super Admin Only)
  // ========================================================================

  /**
   * Get debug data for participants
   * Requires super admin permission
   *
   * @param search - Search by CPF, name or ID membro família
   * @param bypassCache - If true, forces fresh data from BigQuery
   * @returns Debug participant data with protocol metadata
   */
  async getDebugParticipants(search: string, bypassCache: boolean = false): Promise<{ total_found: number; total_returned: number; data: any[] }> {
    const params = new URLSearchParams();
    params.append("search", search);
    if (bypassCache) {
      params.append("bypass_cache", "true");
    }

    const url = `${BASE_URL}/api/v2/debug/participants?${params.toString()}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<{ total_found: number; total_returned: number; data: any[] }>(res, fetchFn);
  },

  // ========================================================================
  // GEOSPATIAL ENDPOINTS
  // ========================================================================

  /**
   * Get all geospatial layers for map visualization
   * Returns equipment (schools, CRAS, clinics) and administrative divisions with GeoJSON geometries
   *
   * @param filters - Filter criteria (tipo_camada, categoria, regional, bairro, regiao_administrativa, subprefeitura)
   * @param bypassCache - If true, forces fresh data from BigQuery
   */
  async getGeospatialLayers(
    filters: Partial<ParticipantFilters> = {},
    bypassCache: boolean = false
  ): Promise<GeospatialLayersResponse> {
    const params = buildFilterParams(filters);
    if (bypassCache) {
      params.append("bypass_cache", "true");
    }

    const url = `${BASE_URL}/api/v2/geospatial/layers?${params.toString()}`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<GeospatialLayersResponse>(res, fetchFn);
  },

  /**
   * V2 — Vocabulario de filtros geoespaciais
   * Chamado 1 vez, staleTime 30min.
   */
  async getGeospatialFilterVocabulary(): Promise<GeospatialFilterVocabularyResponse> {
    const url = `${BASE_URL}/api/v2/geospatial/filters`;

    const fetchFn = () => fetch(url, { cache: "no-store" });
    const res = await fetchFn();

    return handleResponse<GeospatialFilterVocabularyResponse>(res, fetchFn);
  },

};
