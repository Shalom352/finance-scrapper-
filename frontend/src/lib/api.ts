/**
 * UMOA Banking Intelligence — API Client
 *
 * Typed client for the FastAPI backend (/api/v1/*).
 *
 * Pydantic v2 serializes Decimal fields as JSON strings ("3450000.00").
 * Every numeric field is converted here with `toNumberOrNull`, so the UI
 * never receives a string and never turns a missing value into 0.
 */

import type {
  ComparisonResult,
  ComponentProvenance,
  Document,
  FinancialDataDetail,
  FinancialDataPoint,
  GrowthResult,
  Institution,
  InstitutionCoverage,
  MarketShare,
  PaginatedResponse,
  RatioDefinition,
  RatioResult,
  SearchResults,
  SectorAggregation,
  SectorStructure,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Backend hard limit on `page_size` for every paginated route. */
const MAX_PAGE_SIZE = 100;
/** Safety bound for pagination loops (100 pages × 100 rows). */
const MAX_PAGES = 100;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path}`;

  try {
    const response = await fetch(url, { headers: { "Content-Type": "application/json" } });

    if (!response.ok) {
      const text = await response.text().catch(() => "Unknown error");
      throw new ApiError(response.status, text);
    }

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

// ============================================================
// Numeric normalization
// ============================================================

/** Convert a JSON number or Decimal string to a finite number; anything else is `null`. */
export function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function numericFields<T>(obj: T, fields: (keyof T)[]): T {
  const out = { ...obj };
  for (const f of fields) {
    (out as Record<keyof T, unknown>)[f] = toNumberOrNull(obj[f]);
  }
  return out;
}

const normalizeDataPoint = <T extends FinancialDataPoint>(p: T): T =>
  numericFields(p, ["value_normalized"] as (keyof T)[]);

const normalizeComponent = (c: ComponentProvenance): ComponentProvenance =>
  numericFields(c, ["value_normalized"]);

const normalizeRatio = (r: RatioResult): RatioResult => ({
  ...numericFields(r, ["value", "value_percent"]),
  components: (r.components ?? []).map(normalizeComponent),
});

const normalizeGrowth = (g: GrowthResult): GrowthResult => ({
  ...numericFields(g, ["current_value", "previous_value", "absolute_change", "growth_rate", "growth_percent"]),
  components: (g.components ?? []).map(normalizeComponent),
});

const normalizeAggregation = (a: SectorAggregation): SectorAggregation =>
  numericFields(a, ["total_value", "coverage_ratio"]);

const normalizeMarketShare = (m: MarketShare): MarketShare =>
  numericFields(m, [
    "institution_value",
    "sector_total_value",
    "market_share",
    "market_share_percent",
    "coverage_ratio",
  ]);

const normalizeDetail = (d: FinancialDataDetail): FinancialDataDetail =>
  numericFields(normalizeDataPoint(d), ["confidence_score"]);

function mapPage<T>(page: PaginatedResponse<T>, fn: (item: T) => T): PaginatedResponse<T> {
  return { ...page, items: (page.items ?? []).map(fn) };
}

/** Fetch every page of a paginated route until `has_next` is false. */
async function fetchAllPages<T>(
  fetchPage: (page: number) => Promise<PaginatedResponse<T>>,
): Promise<T[]> {
  const all: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const res = await fetchPage(page);
    all.push(...(res.items ?? []));
    if (!res.has_next) return all;
  }
  throw new ApiError(0, "Pagination limit exceeded");
}

// ============================================================
// Institutions
// ============================================================

export async function getInstitutions(params?: {
  page?: number;
  page_size?: number;
  country_code?: string;
  status?: string;
  search?: string;
}): Promise<PaginatedResponse<Institution>> {
  return apiFetch<PaginatedResponse<Institution>>(`/api/v1/institutions${buildQuery({ ...params })}`);
}

/** Every institution (all pages) — used where a complete list is required, e.g. the comparator. */
export async function getInstitutionsAll(params?: { country_code?: string }): Promise<Institution[]> {
  return fetchAllPages((page) => getInstitutions({ ...params, page, page_size: MAX_PAGE_SIZE }));
}

export async function getInstitutionById(id: string): Promise<Institution> {
  return apiFetch<Institution>(`/api/v1/institutions/${encodeURIComponent(id)}`);
}

// ============================================================
// Documents
// ============================================================

export async function getDocuments(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  document_type?: string;
  period_year?: number;
}): Promise<PaginatedResponse<Document>> {
  return apiFetch<PaginatedResponse<Document>>(`/api/v1/documents${buildQuery({ ...params })}`);
}

/** Fiscal years that actually have documents, newest first (scans every document page). */
export async function getDocumentYears(): Promise<number[]> {
  const docs = await fetchAllPages((page) => getDocuments({ page, page_size: MAX_PAGE_SIZE }));
  const years = new Set<number>();
  for (const d of docs) if (typeof d.period_year === "number") years.add(d.period_year);
  return [...years].sort((a, b) => b - a);
}

// ============================================================
// Financial Data
// ============================================================

export interface FinancialDataQuery {
  institution_id?: string;
  metric_code?: string;
  period_type?: string;
  period_year?: number;
  scope?: string;
  status?: string;
}

export async function getFinancialData(
  params?: FinancialDataQuery & { page?: number; page_size?: number },
): Promise<PaginatedResponse<FinancialDataPoint>> {
  const res = await apiFetch<PaginatedResponse<FinancialDataPoint>>(
    `/api/v1/financial-data${buildQuery({ ...params })}`,
  );
  return mapPage(res, normalizeDataPoint);
}

/** Every financial data row matching the filters (no silent truncation at 100 rows). */
export async function getFinancialDataAll(params: FinancialDataQuery): Promise<FinancialDataPoint[]> {
  return fetchAllPages((page) => getFinancialData({ ...params, page, page_size: MAX_PAGE_SIZE }));
}

/** Full provenance record — `GET /api/v1/financial-data/{id}` (backend `FinancialDataRead`). */
export async function getFinancialDataById(id: string): Promise<FinancialDataDetail> {
  const res = await apiFetch<FinancialDataDetail>(`/api/v1/financial-data/${encodeURIComponent(id)}`);
  return normalizeDetail(res);
}

export async function getCoverage(params?: { country_code?: string; institution_id?: string }): Promise<InstitutionCoverage[]> {
  return fetchAllPages((page) =>
    apiFetch<PaginatedResponse<InstitutionCoverage>>(
      `/api/v1/financial-data/coverage${buildQuery({ ...params, page, page_size: MAX_PAGE_SIZE })}`,
    ),
  );
}

/**
 * Fiscal years for which the backend holds financial data, newest first.
 * Derived from `/financial-data/coverage` `available_years` — never invented.
 */
export async function getAvailableYears(params?: { country_code?: string }): Promise<number[]> {
  const coverage = await getCoverage(params);
  const years = new Set<number>();
  for (const c of coverage) for (const y of c.available_years ?? []) years.add(y);
  return [...years].sort((a, b) => b - a);
}

// ============================================================
// Analytics
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
  data_scope?: string;
}): Promise<PaginatedResponse<RatioResult>> {
  const res = await apiFetch<PaginatedResponse<RatioResult>>(`/api/v1/analytics/ratios${buildQuery({ ...params })}`);
  return mapPage(res, normalizeRatio);
}

export async function getGrowth(params?: {
  page?: number;
  page_size?: number;
  institution_id?: string;
  country_code?: string;
  metric_code?: string;
  year?: number;
  data_scope?: string;
}): Promise<PaginatedResponse<GrowthResult>> {
  const res = await apiFetch<PaginatedResponse<GrowthResult>>(`/api/v1/analytics/growth${buildQuery({ ...params })}`);
  return mapPage(res, normalizeGrowth);
}

export async function getAggregations(params: {
  year: number;
  metric_code: string;
  country_code?: string;
  scope?: "country" | "umoa";
}): Promise<SectorAggregation[]> {
  const res = await apiFetch<SectorAggregation[]>(`/api/v1/analytics/aggregations${buildQuery({ ...params })}`);
  return (res ?? []).map(normalizeAggregation);
}

export async function getSectorStructure(params: {
  country_code: string;
  year: number;
  metric_code: string;
}): Promise<SectorStructure> {
  const res = await apiFetch<SectorStructure>(`/api/v1/analytics/sector${buildQuery({ ...params })}`);
  return {
    aggregation: normalizeAggregation(res.aggregation),
    market_shares: (res.market_shares ?? []).map(normalizeMarketShare),
  };
}

export async function getComparison(params: {
  comparison_type: string;
  entity_a: string;
  entity_b: string;
  metric_or_ratio: string;
  year: number;
  data_scope?: string;
}): Promise<ComparisonResult> {
  const res = await apiFetch<ComparisonResult>(`/api/v1/analytics/compare${buildQuery({ ...params })}`);
  return numericFields(res, ["value_a", "value_b", "difference", "ratio_a_to_b"]);
}

// ============================================================
// Search
// ============================================================

export async function searchGlobal(q: string): Promise<SearchResults> {
  return apiFetch<SearchResults>(`/api/v1/search${buildQuery({ q })}`);
}
