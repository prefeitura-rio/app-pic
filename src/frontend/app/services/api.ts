import { signIn } from "next-auth/react";
import {
  PaginatedResponse,
  Participante,
  ProtocoloDetalhes,
  SmartFilterOptions,
  DashboardFilters,
  ParticipantFilters,
} from "../types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL;

/**
 * Handle API response with automatic login redirect on 401
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    // Token expired or invalid - redirect to login automatically
    console.warn("Token expirado ou inválido. Redirecionando para login...");
    signIn("authentik");
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
 * Main API service with only 2 core endpoints:
 * 1. GET /participants/filter-options - Smart filter options with counts
 * 2. GET /participants/ - Paginated participants with filters
 */
export const apiService = {
  /**
   * Get smart filter options with counts for cascading filters.
   * This endpoint is shared between Overview and Professional tabs.
   *
   * @param token - JWT token for authentication
   * @returns SmartFilterOptions with all available filter values and their counts
   */
  async getFilterOptions(
    token?: string
  ): Promise<PaginatedResponse<SmartFilterOptions>> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const url = `${BASE_URL}/api/v1/participants/filter-options`;

    console.log("[API] getFilterOptions - URL:", url);

    const res = await fetch(url, {
      cache: "no-store",
      headers,
    });

    return handleResponse<PaginatedResponse<SmartFilterOptions>>(res);
  },

  /**
   * Get dashboard metrics with filters.
   *
   * @param filters - Filter criteria
   * @param token - JWT token for authentication
   * @returns Dashboard data
   */
  async getDashboard(
    filters: DashboardFilters = {},
    token?: string
  ): Promise<PaginatedResponse<any>> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const params = buildFilterParams(filters);
    const url = `${BASE_URL}/api/v1/dashboard/?${params.toString()}`;

    console.log("[API] getDashboard - Filters:", filters);
    console.log("[API] getDashboard - URL:", url);

    const res = await fetch(url, {
      cache: "no-store",
      headers,
    });

    return handleResponse<PaginatedResponse<any>>(res);
  },

  /**
   * Get participants with filters and pagination.
   * Used by both Overview tab (for calculations) and Professional tab (for table display).
   *
   * @param filters - Filter criteria (bairro, cre, cras, escola, clinica, safra, grupo, status)
   * @param page - Page number (1-indexed)
   * @param pageSize - Items per page
   * @param token - JWT token for authentication
   * @returns Paginated response with participants
   */
  async getParticipants(
    filters: ParticipantFilters = {},
    page: number = 1,
    pageSize: number = 100,
    token?: string
  ): Promise<PaginatedResponse<Participante>> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const params = buildFilterParams(filters);
    params.append("page", page.toString());
    params.append("page_size", pageSize.toString());

    const url = `${BASE_URL}/api/v1/participants/?${params.toString()}`;

    console.log("[API] getParticipants - Filters:", filters);
    console.log("[API] getParticipants - Page:", page, "PageSize:", pageSize);
    console.log("[API] getParticipants - URL:", url);

    const res = await fetch(url, {
      cache: "no-store",
      headers,
    });

    return handleResponse<PaginatedResponse<Participante>>(res);
  },

  /**
   * Get details for a specific participant by CPF.
   *
   * @param cpf - Participant CPF
   * @param token - JWT token for authentication
   * @returns Participant details
   */
  async getParticipantDetails(
    cpf: string,
    token?: string
  ): Promise<Participante> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const url = `${BASE_URL}/api/v1/participants/${cpf}`;

    console.log("[API] getParticipantDetails - CPF:", cpf);
    console.log("[API] getParticipantDetails - URL:", url);

    const res = await fetch(url, {
      cache: "no-store",
      headers,
    });

    const response = await handleResponse<PaginatedResponse<Participante>>(res);

    if (response.data && response.data.length > 0) {
      return response.data[0];
    }

    throw new Error("Participant not found");
  },

  /**
   * Get protocols for a specific participant by CPF.
   *
   * @param cpf - Participant CPF
   * @param token - JWT token for authentication
   * @returns List of protocol details
   */
  async getParticipantProtocols(
    cpf: string,
    token?: string
  ): Promise<ProtocoloDetalhes[]> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const url = `${BASE_URL}/api/v1/participants/${cpf}/protocols`;

    console.log("[API] getParticipantProtocols - CPF:", cpf);
    console.log("[API] getParticipantProtocols - URL:", url);

    const res = await fetch(url, {
      cache: "no-store",
      headers,
    });

    const response = await handleResponse<PaginatedResponse<ProtocoloDetalhes>>(
      res
    );

    return response.data || [];
  },
};
