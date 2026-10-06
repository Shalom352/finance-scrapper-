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
  TargetingQuery,
  TargetingResponse,
  ComponentProvenance,
  ComparisonRow,
  CountryComparison,
  DealAnalytics,
  DealDetail,
  DealDimension,
  DealDuplicate,
  DealListItem,
  DealParticipant,
  Document,
  DuplicateDecision,
  FinancialDataDetail,
  FinancialDataExplorerItem,
  FinancialDataFacets,
  FinancialDataPoint,
  IngestionRun,
  ReviewCenterCounts,
  ReviewAction,
  ReviewDetail,
  ReviewEvent,
  ReviewObservation,
  GrowthResult,
  Institution,
  InstitutionCoverage,
  InstitutionFinancials,
  InstitutionProfileCoverage,
  InstitutionGrowth,
  InstitutionHistory,
  InstitutionRatios,
  InstitutionsComparison,
  MarketShare,
  PaginatedResponse,
  RankHistory,
  RankingResult,
  RatioDefinition,
  RatioResult,
  SearchResults,
  SectorAggregation,
  SectorComparison,
  SectorStructure,
} from "@/types";

/**
 * Browser: the public API URL (inlined at build time). Server components: INTERNAL_API_URL
 * when set (e.g. http://backend:8000 inside Docker), read at runtime, else the public URL.
 */
const API_BASE =
  (typeof window === "undefined" ? process.env.INTERNAL_API_URL : undefined) ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

/** Backend hard limit on `page_size` for every paginated route. */
const MAX_PAGE_SIZE = 100;
/** Safety bound for pagination loops (100 pages × 100 rows). */
const MAX_PAGES = 100;

/**
 * status 0 = network failure (no answer). `code` / `message` come from the backend envelope
 * `{ error: { code, message } }` when present; they are for logic and diagnostics — the UI
 * always shows its own translated message, never a raw backend text.
 */
export class ApiError extends Error {
  public code: string;

  constructor(
    public status: number,
    message: string,
    code?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code ?? (status === 0 ? "NETWORK_ERROR" : `HTTP_${status}`);
  }
}

/** Build an ApiError from a non-2xx response, reading the backend error envelope when present. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => "");
  try {
    const body = JSON.parse(text) as { error?: { code?: unknown; message?: unknown }; detail?: unknown };
    const code = typeof body.error?.code === "string" ? body.error.code : undefined;
    const raw = body.error?.message ?? body.detail;
    const message = typeof raw === "string" ? raw : `HTTP ${response.status}`;
    return new ApiError(response.status, message, code);
  } catch {
    return new ApiError(response.status, `HTTP ${response.status}`);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch {
    // An answer was received but is not valid JSON: not a network failure.
    throw new ApiError(response.status, "Invalid JSON response", "INVALID_RESPONSE");
  }
}

async function apiFetch<T>(path: string): Promise<T> {
  let response: Response;
  try {
    // No Content-Type on a GET: nothing is sent, and it would force a CORS preflight.
    response = await fetch(`${API_BASE}${path}`, { headers: { Accept: "application/json" } });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }
  if (!response.ok) throw await errorFromResponse(response);
  return readJson<T>(response);
}

/** POST JSON; a non-2xx answer becomes an ApiError carrying the HTTP status (404 / 409 / 422…). */
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }
  if (!response.ok) throw await errorFromResponse(response);
  return readJson<T>(response);
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

// Data explorer (Phase 11) — same list route, extended filters / sort / provenance summary.

export type ExplorerSort = "institution" | "country" | "indicator" | "year" | "value";

export interface FinancialDataExplorerQuery extends FinancialDataQuery {
  institution_ids?: string[];
  country_code?: string;
  currency_normalized?: string;
  sort?: ExplorerSort;
  order?: "asc" | "desc";
}

/** Explorer params: rejected rows are never listed as valid data (only on an explicit status filter). */
function explorerQuery({ institution_ids, ...rest }: FinancialDataExplorerQuery) {
  return { ...rest, institution_ids: institution_ids?.join(","), include_rejected: false };
}

export async function getFinancialDataExplorer(
  params: FinancialDataExplorerQuery & { page?: number; page_size?: number },
): Promise<PaginatedResponse<FinancialDataExplorerItem>> {
  const res = await apiFetch<PaginatedResponse<FinancialDataExplorerItem>>(
    `/api/v1/financial-data${buildQuery(explorerQuery(params))}`,
  );
  return mapPage(res, normalizeDataPoint);
}

export async function getFinancialDataFacets(): Promise<FinancialDataFacets> {
  return apiFetch<FinancialDataFacets>("/api/v1/financial-data/facets");
}

export type CsvExportResult = { status: "ok"; blob: Blob } | { status: "too_large" };

/** CSV of the filtered rows (backend-bounded). HTTP 413 → too_large: refine the filters. */
export async function exportFinancialDataCsv(params: FinancialDataExplorerQuery): Promise<CsvExportResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/financial-data/export${buildQuery(explorerQuery(params))}`);
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }
  if (response.status === 413) return { status: "too_large" };
  if (!response.ok) throw await errorFromResponse(response);
  return { status: "ok", blob: await response.blob() };
}

// ============================================================
// Data Quality & Review Center (Phase 12)
// ============================================================

/** Review queue: without a status, the observations needing a decision (needs_review + conflicts). */
export async function getDataQualityQueue(
  params: FinancialDataExplorerQuery & { page?: number; page_size?: number },
): Promise<PaginatedResponse<FinancialDataExplorerItem>> {
  const { institution_ids, ...rest } = params;
  const res = await apiFetch<PaginatedResponse<FinancialDataExplorerItem>>(
    `/api/v1/data-quality${buildQuery({ ...rest, institution_ids: institution_ids?.join(",") })}`,
  );
  return mapPage(res, normalizeDataPoint);
}

export async function getDataQualityCounts(): Promise<ReviewCenterCounts> {
  return apiFetch<ReviewCenterCounts>("/api/v1/data-quality/summary");
}

const normalizeEvent = (e: ReviewEvent): ReviewEvent => numericFields(e, ["value_before", "value_after"]);

const normalizeReviewObservation = (o: ReviewObservation): ReviewObservation =>
  numericFields(o, ["value_normalized", "difference"]);

export async function getReviewDetail(id: string): Promise<ReviewDetail> {
  const d = await apiFetch<ReviewDetail>(`/api/v1/data-quality/${encodeURIComponent(id)}`);
  return {
    ...d,
    observation: normalizeDetail(d.observation),
    competing: (d.competing ?? []).map(normalizeReviewObservation),
    not_comparable: (d.not_comparable ?? []).map(normalizeReviewObservation),
    allowed_actions: d.allowed_actions ?? [],
  };
}

export async function getReviewHistory(id: string): Promise<ReviewEvent[]> {
  const rows = await apiFetch<ReviewEvent[]>(`/api/v1/data-quality/${encodeURIComponent(id)}/history`);
  return (rows ?? []).map(normalizeEvent);
}

export interface ReviewDecision {
  actor: string;
  reason: string;
  /** State the reviewer saw: the backend answers 409 if it changed meanwhile. */
  expected_status: string;
  expected_updated_at: string;
}

/** A human decision. The resulting status is decided by the backend, never sent. */
export async function postReviewAction(
  id: string,
  action: ReviewAction,
  decision: ReviewDecision,
): Promise<FinancialDataDetail> {
  const res = await apiPost<FinancialDataDetail>(`/api/v1/data-quality/${encodeURIComponent(id)}/${action}`, decision);
  return normalizeDetail(res);
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

/**
 * Default fiscal year for sector views: the requested year when it exists, otherwise the
 * newest year whose total assets aggregate is actually computable (a year holding only
 * values still to review has no admissible aggregate). Falls back to the newest year.
 */
export async function resolveSectorYear(
  requested: number | null,
  years: number[],
  country_code?: string,
): Promise<number | null> {
  if (requested !== null && years.includes(requested)) return requested;
  for (const y of [...years].sort((a, b) => b - a)) {
    const aggs = await getAggregations(
      country_code ? { year: y, metric_code: "total_actifs", country_code } : { year: y, metric_code: "total_actifs", scope: "umoa" },
    ).catch(() => []);
    if (aggs.some((a) => a.metric_code === "total_actifs" && a.year === y && a.total_value !== null)) return y;
  }
  return years.length > 0 ? Math.max(...years) : null;
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

// ============================================================
// Search
// ============================================================

export async function searchGlobal(q: string): Promise<SearchResults> {
  return apiFetch<SearchResults>(`/api/v1/search${buildQuery({ q })}`);
}

// ============================================================
// Phase 9 — Descriptive rankings & comparisons
// ============================================================

export interface RankingQuery {
  metric_code: string;
  period_year?: number;
  period_type?: string;
  data_scope?: string;
  country_code?: string;
  order?: "desc" | "asc";
  page?: number;
  page_size?: number;
}

const normalizeRow = <T extends { value: number | null }>(r: T): T => numericFields(r, ["value"] as (keyof T)[]);

export async function getRankings(params: RankingQuery): Promise<RankingResult> {
  const res = await apiFetch<RankingResult>(`/api/v1/rankings${buildQuery({ ...params })}`);
  return { ...res, items: (res.items ?? []).map(normalizeRow) };
}

export async function getRankHistory(params: {
  institution_id: string;
  metric_code: string;
  period_type?: string;
  data_scope?: string;
  country_code?: string;
}): Promise<RankHistory> {
  const res = await apiFetch<RankHistory>(`/api/v1/rankings/history${buildQuery({ ...params })}`);
  return { ...res, points: (res.points ?? []).map(normalizeRow) };
}

export async function getInstitutionsComparison(params: {
  institution_ids: string[];
  metric_code: string;
  period_year?: number;
  period_type?: string;
  data_scope?: string;
}): Promise<InstitutionsComparison> {
  const { institution_ids, ...rest } = params;
  const res = await apiFetch<InstitutionsComparison>(
    `/api/v1/comparisons${buildQuery({ ...rest, institution_ids: institution_ids.join(",") })}`,
  );
  return { ...res, rows: (res.rows ?? []).map((r: ComparisonRow) => normalizeRow(r)) };
}

export async function getSectorComparison(params: {
  institution_id: string;
  metric_code: string;
  period_year?: number;
}): Promise<SectorComparison> {
  const res = await apiFetch<SectorComparison>(`/api/v1/comparisons/sector${buildQuery({ ...params })}`);
  return {
    ...numericFields(res, ["sector_total", "share_percent", "sector_coverage_ratio"]),
    institution: res.institution ? normalizeRow(res.institution) : null,
  };
}

export async function getCountryComparison(params: {
  country_code: string;
  metric_code: string;
  period_year?: number;
}): Promise<CountryComparison> {
  const res = await apiFetch<CountryComparison>(`/api/v1/comparisons/country${buildQuery({ ...params })}`);
  return numericFields(res, [
    "country_total",
    "umoa_total",
    "share_percent",
    "country_coverage_ratio",
    "umoa_coverage_ratio",
  ]);
}

// ============================================================
// Phase 10 — Institution financial profile (backend-qualified)
// ============================================================

export interface ProfileQuery {
  period_year?: number;
  period_type?: string;
  data_scope?: string;
  indicator?: string;
}

function institutionPath(id: string, resource: string, params: ProfileQuery): string {
  return `/api/v1/institutions/${encodeURIComponent(id)}/${resource}${buildQuery({ ...params })}`;
}

export async function getInstitutionFinancials(id: string, params: ProfileQuery = {}): Promise<InstitutionFinancials> {
  const res = await apiFetch<InstitutionFinancials>(institutionPath(id, "financials", params));
  return { ...res, values: (res.values ?? []).map((v) => numericFields(v, ["value_normalized"])) };
}

export async function getInstitutionHistory(id: string, params: ProfileQuery = {}): Promise<InstitutionHistory> {
  const res = await apiFetch<InstitutionHistory>(institutionPath(id, "history", params));
  return {
    ...res,
    series: (res.series ?? []).map((s) => ({ ...s, points: (s.points ?? []).map((p) => numericFields(p, ["value"])) })),
  };
}

export async function getInstitutionRatios(id: string, params: ProfileQuery = {}): Promise<InstitutionRatios> {
  const res = await apiFetch<InstitutionRatios>(institutionPath(id, "ratios", params));
  return { ...res, items: (res.items ?? []).map(normalizeRatio) };
}

export async function getInstitutionGrowth(id: string, params: ProfileQuery = {}): Promise<InstitutionGrowth> {
  const res = await apiFetch<InstitutionGrowth>(institutionPath(id, "growth", params));
  return { ...res, items: (res.items ?? []).map(normalizeGrowth) };
}

export async function getInstitutionCoverage(id: string, params: ProfileQuery = {}): Promise<InstitutionProfileCoverage> {
  const res = await apiFetch<InstitutionProfileCoverage>(institutionPath(id, "coverage", params));
  return numericFields(res, ["coverage_ratio"]);
}


// ============================================================
// Phase 13 — Deal Intelligence (read) + Review Center decisions on deals
// ============================================================

export interface DealQuery {
  country?: string;
  bank?: string;
  deal_type?: string;
  sector?: string;
  year?: number;
  currency?: string;
  status?: string;
  participant_role?: string;
  borrower?: string;
  arranger?: string;
  include_merged?: boolean;
}

const normalizeParticipant = (p: DealParticipant): DealParticipant => numericFields(p, ["commitment_amount"]);

const normalizeDealItem = <T extends DealListItem>(d: T): T => ({
  ...numericFields(d, ["amount"] as (keyof T)[]),
  borrowers: d.borrowers ?? [],
  arrangers: d.arrangers ?? [],
});

const normalizeDeal = (d: DealDetail): DealDetail => ({
  ...normalizeDealItem(numericFields(d, ["interest_rate", "spread_bps"])),
  participants: (d.participants ?? []).map(normalizeParticipant),
  sources: d.sources ?? [],
  field_provenance: d.field_provenance ?? {},
  duplicates: (d.duplicates ?? []).map((c) => ({ ...c, matched_criteria: c.matched_criteria ?? [] })),
  merged_deals: (d.merged_deals ?? []).map((m) => ({
    ...m,
    sources: m.sources ?? [],
    participants: (m.participants ?? []).map(normalizeParticipant),
  })),
  allowed_actions: d.allowed_actions ?? [],
});

export async function getDeals(
  params: DealQuery & { page?: number; page_size?: number },
): Promise<PaginatedResponse<DealListItem>> {
  const res = await apiFetch<PaginatedResponse<DealListItem>>(`/api/v1/deals${buildQuery({ ...params })}`);
  return mapPage(res, normalizeDealItem);
}

export async function getDeal(id: string): Promise<DealDetail> {
  return normalizeDeal(await apiFetch<DealDetail>(`/api/v1/deals/${encodeURIComponent(id)}`));
}

export async function getDealHistory(id: string): Promise<ReviewEvent[]> {
  const rows = await apiFetch<ReviewEvent[]>(`/api/v1/deals/${encodeURIComponent(id)}/history`);
  return (rows ?? []).map(normalizeEvent);
}

export async function getDealAnalytics(dimension: DealDimension): Promise<DealAnalytics> {
  const res = await apiFetch<DealAnalytics>(`/api/v1/deals/analytics${buildQuery({ dimension })}`);
  return {
    ...res,
    rows: (res.rows ?? []).map((r) => ({
      ...r,
      by_status: r.by_status ?? {},
      amounts: (r.amounts ?? []).map((a) => numericFields(a, ["total"])),
    })),
  };
}

export async function getDealQueue(params: {
  status?: string;
  country?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<DealListItem>> {
  const res = await apiFetch<PaginatedResponse<DealListItem>>(
    `/api/v1/data-quality/deals${buildQuery({ ...params })}`,
  );
  return mapPage(res, normalizeDealItem);
}

export async function getOpenDealDuplicates(
  params: { page?: number; page_size?: number } = {},
): Promise<PaginatedResponse<DealDuplicate>> {
  const res = await apiFetch<PaginatedResponse<DealDuplicate>>(
    `/api/v1/data-quality/deal-duplicates${buildQuery({ ...params })}`,
  );
  return mapPage(res, (c) => ({ ...c, matched_criteria: c.matched_criteria ?? [] }));
}

/** A human decision on a deal. The resulting status is decided by the backend. */
export async function postDealReviewAction(
  id: string,
  action: ReviewAction,
  decision: ReviewDecision,
): Promise<DealDetail> {
  return normalizeDeal(
    await apiPost<DealDetail>(`/api/v1/data-quality/deals/${encodeURIComponent(id)}/${action}`, decision),
  );
}

/** Human decision on a duplicate candidate: never an automatic merge, never a deletion. */
export async function postDuplicateDecision(
  candidateId: string,
  body: { decision: DuplicateDecision; primary_deal_id?: string; actor: string; reason: string },
): Promise<DealDuplicate> {
  return apiPost<DealDuplicate>(`/api/v1/data-quality/deal-duplicates/${encodeURIComponent(candidateId)}/decide`, {
    ...body,
    expected_state: "duplicate_candidate",
  });
}

/** Get the latest automated/manual ingestion run execution details. */
export async function getLatestIngestionRun(): Promise<IngestionRun | null> {
  try {
    return await apiFetch<IngestionRun | null>("/api/v1/ingestion/runs/latest");
  } catch {
    return null;
  }
}


// Phase 20 — targeting (explicit criteria, no score).
export async function getTargeting(query: TargetingQuery): Promise<TargetingResponse> {
  const res = await apiFetch<TargetingResponse>(`/api/v1/targeting${buildQuery({ ...query })}`);
  return { ...res, items: res.items ?? [] };
}

/** Phase 21 — a human withdraws an automatic validation (back to needs_review, never re-validated). */
export async function postRevokeAutomatic(
  kind: "observation" | "deal",
  id: string,
  decision: { actor: string; reason: string; expected_status: string },
): Promise<unknown> {
  const path = kind === "deal"
    ? `/api/v1/data-quality/deals/${encodeURIComponent(id)}/revoke-automatic`
    : `/api/v1/data-quality/${encodeURIComponent(id)}/revoke-automatic`;
  return apiPost<unknown>(path, decision);
}
