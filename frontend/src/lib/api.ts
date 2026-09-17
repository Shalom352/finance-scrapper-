/**
 * UMOA Banking Intelligence — API Client
 *
 * Typed client for communicating with the FastAPI backend.
 */

import type { HealthResponse, PaginatedResponse, Institution, Document } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ============================================================
// Core fetch wrapper
// ============================================================

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;

  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "Unknown error");
    throw new ApiError(response.status, text);
  }

  return response.json() as Promise<T>;
}

// ============================================================
// Health
// ============================================================

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export async function getFullHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/v1/health");
}

// ============================================================
// Institutions (Phase 1 — endpoints not yet implemented)
// ============================================================

export async function getInstitutions(params?: {
  page?: number;
  page_size?: number;
  country_code?: string;
}): Promise<PaginatedResponse<Institution>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.country_code) query.set("country_code", params.country_code);

  return apiFetch<PaginatedResponse<Institution>>(`/api/v1/institutions/?${query}`);
}

// ============================================================
// Documents (Phase 2 — endpoints not yet implemented)
// ============================================================

export async function getDocuments(params?: {
  page?: number;
  institution_id?: string;
}): Promise<PaginatedResponse<Document>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.institution_id) query.set("institution_id", params.institution_id);

  return apiFetch<PaginatedResponse<Document>>(`/api/v1/documents/?${query}`);
}
