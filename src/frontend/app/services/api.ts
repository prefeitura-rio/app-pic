import { Individual, PaginatedResponse, BackendResponse, DashboardSummary, FilterOption } from "../types";
import { signIn } from "next-auth/react";

const API_BASE_URL = "/api/v1"; 

// Helper to handle response
async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    // Token expired or invalid, redirect to login
    if (typeof window !== "undefined") {
      signIn("authentik"); 
    }
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }
  return response.json();
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL;

export interface DashboardFilters {
  bairro?: string;
  cre?: string;
  cras?: string;
  safra?: string;
  grupo?: string;
  status?: string;
}

export const apiService = {
  async getFilterOptions(token?: string): Promise<FilterOption[]> {
     const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const res = await fetch(`${BASE_URL}/api/v1/filters/options`, {
      cache: "no-store",
      headers,
    });
    const response = await handleResponse<{ options: FilterOption[] }>(res);
    return response.options;
  },

  async getDashboardMetrics(filters: DashboardFilters = {}, token?: string): Promise<DashboardSummary> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const params = new URLSearchParams();
    if (filters.bairro && filters.bairro !== "todos") params.append("bairro", filters.bairro);
    if (filters.cre && filters.cre !== "todas") params.append("cre", filters.cre);
    if (filters.cras && filters.cras !== "todas") params.append("cras", filters.cras);
    if (filters.safra && filters.safra !== "todas") params.append("safra", filters.safra);
    if (filters.grupo && filters.grupo !== "todos") params.append("grupo", filters.grupo);
    if (filters.status && filters.status !== "todos") params.append("status", filters.status);

    const res = await fetch(`${BASE_URL}/api/v1/dashboard/?${params.toString()}`, {
      cache: "no-store",
      headers,
    });
    // The API returns a list of summaries (usually 1 item) wrapped in BackendResponse
    const response = await handleResponse<BackendResponse<DashboardSummary>>(res);
    if (response.data && response.data.length > 0) {
      return response.data[0];
    }
    throw new Error("No dashboard summary data returned");
  },

  async getParticipants(page: number = 1, pageSize: number = 50, token?: string): Promise<PaginatedResponse<Individual>> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    
    const res = await fetch(`${BASE_URL}/api/v1/participants/?page=${page}&page_size=${pageSize}`, {
      cache: "no-store",
      headers,
    });
    return handleResponse<PaginatedResponse<Individual>>(res);
  },

  async getParticipantDetails(cpf: string, token?: string): Promise<Individual> {
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${BASE_URL}/api/v1/participants/${cpf}`, {
      cache: "no-store",
      headers,
    });
    const response = await handleResponse<BackendResponse<Individual>>(res);
    if (response.data && response.data.length > 0) {
        return response.data[0];
    }
    throw new Error("Participant not found");
  }
};
