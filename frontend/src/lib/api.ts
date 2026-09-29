/**
 * UMOA Banking Intelligence — Comprehensive API Client
 *
 * Fully typed client communicating with FastAPI backend (/api/v1/*).
 */

import type {
  ComparisonResult,
  Country,
  Document,
  FinancialDataPoint,
  GrowthResult,
  HealthResponse,
  Institution,
  MetricDefinition,
  PaginatedResponse,
  RatioDefinition,
  RatioResult,
  SearchResults,
  SectorAggregation,
  SectorStructure,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
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

  try {
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

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(500, err instanceof Error ? err.message : "Network error");
  }
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
// Countries
// ============================================================

export async function getCountries(): Promise<PaginatedResponse<Country>> {
  return apiFetch<PaginatedResponse<Country>>("/api/v1/countries");
}

export async function getCountryById(id: string): Promise<Country> {
  return apiFetch<Country>(`/api/v1/countries/${id}`);
}

// ============================================================
// Institutions
// ============================================================

export async function getInstitutions(params?: {
  page?: number;
  page_size?: number;
  country_code?: string;
  banking_group_id?: string;
  status?: string;
  search?: string;
}): Promise<PaginatedResponse<Institution>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.country_code) query.set("country_code", params.country_code);
  if (params?.banking_group_id) query.set("banking_group_id", params.banking_group_id);
  if (params?.status) query.set("status", params.status);
  if (params?.search) query.set("search", params.search);

  return apiFetch<PaginatedResponse<Institution>>(`/api/v1/institutions?${query}`);
}

export async function getInstitutionById(id: string): Promise<Institution> {
  return apiFetch<Institution>(`/api/v1/institutions/${id}`);
}

// ============================================================
// Documents
// ============================================================

export async function getDocuments(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  source_id?: string;
  document_type?: string;
  period_year?: number;
  download_status?: string;
}): Promise<PaginatedResponse<Document>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.institution_id) query.set("institution_id", params.institution_id);
  if (params?.source_id) query.set("source_id", params.source_id);
  if (params?.document_type) query.set("document_type", params.document_type);
  if (params?.period_year) query.set("period_year", String(params.period_year));
  if (params?.download_status) query.set("download_status", params.download_status);

  return apiFetch<PaginatedResponse<Document>>(`/api/v1/documents?${query}`);
}

export async function getDocumentById(id: string): Promise<Document> {
  return apiFetch<Document>(`/api/v1/documents/${id}`);
}

// ============================================================
// Financial Data
// ============================================================

export async function getFinancialData(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  metric_code?: string;
  period_year?: number;
  status?: string;
}): Promise<PaginatedResponse<FinancialDataPoint>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.institution_id) query.set("institution_id", params.institution_id);
  if (params?.metric_code) query.set("metric_code", params.metric_code);
  if (params?.period_year) query.set("period_year", String(params.period_year));
  if (params?.status) query.set("status", params.status);

  return apiFetch<PaginatedResponse<FinancialDataPoint>>(`/api/v1/financial-data?${query}`);
}

export async function getFinancialDataById(id: string): Promise<FinancialDataPoint> {
  return apiFetch<FinancialDataPoint>(`/api/v1/financial-data/${id}`);
}

export async function getMetricDefinitions(): Promise<PaginatedResponse<MetricDefinition>> {
  return apiFetch<PaginatedResponse<MetricDefinition>>("/api/v1/metrics");
}

// ============================================================
// Phase 7 Analytics
// ============================================================

export async function getRatioDefinitions(): Promise<RatioDefinition[]> {
  return apiFetch<RatioDefinition[]>("/api/v1/analytics/definitions");
}

export async function getRatios(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  country_code?: string;
  ratio_code?: string;
  year?: number;
  status?: string;
}): Promise<PaginatedResponse<RatioResult>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.institution_id) query.set("institution_id", params.institution_id);
  if (params?.country_code) query.set("country_code", params.country_code);
  if (params?.ratio_code) query.set("ratio_code", params.ratio_code);
  if (params?.year) query.set("year", String(params.year));
  if (params?.status) query.set("status", params.status);

  return apiFetch<PaginatedResponse<RatioResult>>(`/api/v1/analytics/ratios?${query}`);
}

export async function getGrowth(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  country_code?: string;
  metric_code?: string;
  year?: number;
  status?: string;
}): Promise<PaginatedResponse<GrowthResult>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.institution_id) query.set("institution_id", params.institution_id);
  if (params?.country_code) query.set("country_code", params.country_code);
  if (params?.metric_code) query.set("metric_code", params.metric_code);
  if (params?.year) query.set("year", String(params.year));
  if (params?.status) query.set("status", params.status);

  return apiFetch<PaginatedResponse<GrowthResult>>(`/api/v1/analytics/growth?${query}`);
}

export async function getAggregations(params: {
  year: number;
  metric_code?: string;
  country_code?: string;
  scope?: "country" | "umoa";
  include_needs_review?: boolean;
}): Promise<SectorAggregation[]> {
  const query = new URLSearchParams();
  query.set("year", String(params.year));
  if (params.metric_code) query.set("metric_code", params.metric_code);
  if (params.country_code) query.set("country_code", params.country_code);
  if (params.scope) query.set("scope", params.scope);
  if (params.include_needs_review) query.set("include_needs_review", "true");

  return apiFetch<SectorAggregation[]>(`/api/v1/analytics/aggregations?${query}`);
}

export async function getSectorStructure(params: {
  country_code: string;
  year: number;
  metric_code?: string;
}): Promise<SectorStructure> {
  const query = new URLSearchParams();
  query.set("country_code", params.country_code);
  query.set("year", String(params.year));
  if (params.metric_code) query.set("metric_code", params.metric_code);

  return apiFetch<SectorStructure>(`/api/v1/analytics/sector?${query}`);
}

export async function getComparison(params: {
  comparison_type: string;
  entity_a: string;
  entity_b: string;
  metric_or_ratio: string;
  year: number;
}): Promise<ComparisonResult> {
  const query = new URLSearchParams();
  query.set("comparison_type", params.comparison_type);
  query.set("entity_a", params.entity_a);
  query.set("entity_b", params.entity_b);
  query.set("metric_or_ratio", params.metric_or_ratio);
  query.set("year", String(params.year));

  return apiFetch<ComparisonResult>(`/api/v1/analytics/compare?${query}`);
}

// ============================================================
// Search
// ============================================================

export async function searchGlobal(q: string): Promise<SearchResults> {
  const query = new URLSearchParams({ q });
  return apiFetch<SearchResults>(`/api/v1/search?${query}`);
}
