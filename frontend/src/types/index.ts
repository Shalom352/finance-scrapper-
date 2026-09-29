/**
 * UMOA Banking Intelligence — TypeScript Types
 *
 * Mirrors the backend Pydantic schemas (app/schemas/*, app/api/v1/search.py).
 * Pydantic v2 serializes Decimal fields as JSON strings: api.ts converts them
 * to `number | null` on reception, so every monetary field below is numeric.
 * A missing value is always `null` — never 0.
 */

// ============================================================
// Common & Locales
// ============================================================

export type Locale = "fr" | "en";

export type DataStatus =
  | "extracted"
  | "needs_review"
  | "reviewed"
  | "verified"
  | "rejected"
  | "unavailable";

export type RatioStatus =
  | "calculated"
  | "calculated_from_verified"
  | "needs_review"
  | "unavailable";

export type PeriodType = "annual" | "semi_annual" | "quarterly";
export type DataScope = "individual" | "consolidated";

// ============================================================
// UMOA Geography
// ============================================================

export type UMOACountryCode = "BJ" | "BF" | "CI" | "GW" | "ML" | "NE" | "SN" | "TG";

/** Backend `CountryList` — the ISO code is exposed as `code`. */
export interface Country {
  id: string;
  code: string;
  name_fr: string;
  name_en: string;
  flag_emoji?: string | null;
  is_active: boolean;
}

// ============================================================
// Sources & Groups
// ============================================================

export interface SourceList {
  id: string;
  name: string;
  short_name?: string | null;
  source_type: string;
  priority: number;
  country_code?: string | null;
  is_active: boolean;
}

export interface BankingGroupList {
  id: string;
  name: string;
  short_name?: string | null;
  headquarter_country_code?: string | null;
}

// ============================================================
// Institutions
// ============================================================

export interface Institution {
  id: string;
  name_official: string;
  name_commercial?: string | null;
  institution_type: string;
  country_id: string;
  country?: Country | null;
  banking_group_id?: string | null;
  banking_group?: BankingGroupList | null;
  regulatory_id?: string | null;
  website_url?: string | null;
  status: string;
  description?: string | null;
  data_notes?: string | null;
  source_id?: string | null;
  source?: SourceList | null;
  created_at?: string;
  updated_at?: string;
}

// ============================================================
// Documents
// ============================================================

/** Backend `DocumentList`. Nested source/institution only exist on `DocumentRead`. */
export interface Document {
  id: string;
  title: string;
  document_type: string;
  institution_id?: string | null;
  source_id: string;
  url?: string | null;
  period_year?: number | null;
  period_type?: string | null;
  language?: string | null;
  download_status: string;
  extraction_status: string;
}

// ============================================================
// Financial Data
// ============================================================

/** Backend `FinancialDataList` — no provenance fields in list responses. */
export interface FinancialDataPoint {
  id: string;
  institution_id: string;
  metric_code: string;
  scope: DataScope | string;
  period_type: PeriodType | string;
  period_year: number;
  period_label?: string | null;
  value_original: string;
  unit_original?: string | null;
  currency_original?: string | null;
  value_normalized: number | null;
  unit_normalized?: string | null;
  currency_normalized?: string | null;
  extraction_method: string;
  status: DataStatus | string;
}

export interface MetricList {
  id: string;
  code: string;
  label_fr: string;
  label_en: string;
  statement_type: string;
  category: string;
  value_type: string;
  currency_type: string;
  is_calculated: boolean;
  is_active: boolean;
  is_debt_related: boolean;
  display_order: number;
}

/** Backend `FinancialDataRead` — `GET /api/v1/financial-data/{id}`. Full provenance. */
export interface FinancialDataDetail extends FinancialDataPoint {
  source_id: string;
  document_id: string;
  page_number: number | null;
  confidence_score: number | null;
  notes: string | null;
  extracted_at: string | null;
  verified_at: string | null;
  verified_by: string | null;
  created_at: string;
  updated_at: string;
  institution: Institution | null;
  source: SourceList | null;
  document: Document | null;
  metric: MetricList | null;
}

/** Backend `InstitutionCoverageResponse` — `GET /api/v1/financial-data/coverage`. */
export interface InstitutionCoverage {
  institution_id: string;
  institution_name: string;
  country_code: string;
  first_year: number | null;
  last_year: number | null;
  available_years: number[];
  missing_years: number[];
  coverage_ratio: number | null;
  metrics_available_count: number;
  documents_available_count: number;
  data_points_count: number;
}

// ============================================================
// Analytics & Ratios
// ============================================================

export interface ComponentProvenance {
  data_id: string;
  metric_code: string;
  period_year: number;
  period_type: string;
  scope?: string | null;
  value_normalized: number | null;
  currency?: string | null;
  source_id?: string | null;
  source_name?: string | null;
  document_id?: string | null;
  page_number?: number | null;
  status: string;
  role?: string | null;
}

export interface RatioDefinition {
  ratio_code: string;
  name_fr: string;
  name_en: string;
  description_fr: string;
  description_en: string;
  formula: string;
  numerator_metric: string;
  denominator_metric: string;
  requires_average_denominator: boolean;
  unit: string;
  frequency: string;
  required_metrics: string[];
  eligibility_rules: string[];
}

export interface RatioResult {
  ratio_code: string;
  ratio_name: string;
  institution_id: string;
  institution_name?: string | null;
  country_code?: string | null;
  period_year: number;
  period_type: string;
  data_scope?: string | null;
  value: number | null;
  value_percent: number | null;
  unit: string;
  status: RatioStatus | string;
  reason?: string | null;
  formula_used: string;
  components: ComponentProvenance[];
  calculated_at: string;
}

export interface GrowthResult {
  metric_code: string;
  metric_label?: string | null;
  institution_id: string;
  institution_name?: string | null;
  country_code?: string | null;
  current_year: number;
  previous_year: number;
  data_scope?: string | null;
  current_value: number | null;
  previous_value: number | null;
  absolute_change: number | null;
  growth_rate: number | null;
  growth_percent: number | null;
  currency?: string | null;
  status: string;
  reason?: string | null;
  components: ComponentProvenance[];
  calculated_at: string;
}

export interface SectorAggregation {
  scope: "country" | "umoa" | string;
  country_code?: string | null;
  country_name?: string | null;
  year: number;
  metric_code: string;
  metric_label?: string | null;
  total_value: number | null;
  currency: string | null;
  /** Accounting scope aggregated (Phase 8C: always "individual"). */
  data_scope?: string;
  period_type?: string;
  institution_count: number;
  total_institutions: number;
  coverage_ratio: number | null;
  is_partial: boolean;
  status: string;
  contributing_institutions: string[];
  notes?: string | null;
}

export interface MarketShare {
  institution_id: string;
  institution_name?: string | null;
  country_code: string;
  year: number;
  metric_code: string;
  institution_value: number | null;
  sector_total_value: number | null;
  market_share: number | null;
  market_share_percent: number | null;
  currency: string | null;
  coverage_ratio: number | null;
  status: string;
}

export interface SectorStructure {
  aggregation: SectorAggregation;
  market_shares: MarketShare[];
}

export interface ComparisonResult {
  comparison_type: string;
  entity_a: string;
  entity_b: string;
  metric_or_ratio: string;
  year: number;
  value_a: number | null;
  value_b: number | null;
  unit?: string | null;
  difference: number | null;
  ratio_a_to_b: number | null;
  description: string;
}

// ============================================================
// Search & API Responses
// ============================================================

/** Backend `SearchResults` (app/api/v1/search.py) — no metrics are indexed. */
export interface SearchResults {
  query: string;
  total: number;
  institutions: Institution[];
  banking_groups: BankingGroupList[];
  sources: SourceList[];
  documents: Document[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  env: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

// ============================================================
// Phase 9 — Descriptive rankings & comparisons
// ============================================================

export type RankingStatus = "calculated" | "partial" | "needs_review" | "unavailable";

/** Traceability of one observation behind a ranked or compared value. */
export interface ProvenanceRef {
  data_id: string;
  metric_code: string;
  period_year: number;
  period_type: string;
  scope?: string | null;
  source_id?: string | null;
  source_name?: string | null;
  document_id?: string | null;
  document_title?: string | null;
  page_number?: number | null;
  status: string;
  role?: string | null;
}

export interface RankingCoverage {
  /** Institutions with an admissible value (real count, never forced to 0). */
  eligible_count: number;
  /** Institutions actually ranked (0 when the ranking cannot be computed). */
  ranked_count: number;
  expected_count: number;
  /** null when nobody is expected or the ranking cannot be computed — never 0/N. */
  coverage_ratio: number | null;
  coverage_status: "available" | "unavailable";
}

export interface RankingEntry {
  rank: number;
  institution_id: string;
  institution_name: string;
  country_code?: string | null;
  metric_code: string;
  period_year: number;
  period_type: string;
  data_scope: string;
  value: number | null;
  unit: string;
  currency?: string | null;
  status: string;
  data_id?: string | null;
  provenance: ProvenanceRef[];
}

/** Institution without an admissible value: listed, never ranked. */
export interface RankingUnavailableEntry {
  institution_id: string;
  institution_name: string;
  country_code?: string | null;
  status: string;
  reason: string;
  detail?: string | null;
  currency?: string | null;
}

export interface RankingResult {
  metric_code: string;
  kind: "metric" | "growth" | "ratio" | string;
  unit: string;
  country_code: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  order: "desc" | "asc" | string;
  status: RankingStatus;
  reason?: string | null;
  currency?: string | null;
  coverage: RankingCoverage;
  items: RankingEntry[];
  total_ranked: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
  unavailable: RankingUnavailableEntry[];
  available_years: number[];
}

export interface RankHistoryPoint {
  period_year: number;
  rank: number | null;
  value: number | null;
  currency?: string | null;
  ranking_status: RankingStatus;
  status: string;
  reason?: string | null;
  eligible_count: number;
  ranked_count: number;
  expected_count: number;
  coverage_ratio: number | null;
}

export interface RankHistory {
  institution_id: string;
  institution_name: string;
  metric_code: string;
  period_type: string;
  data_scope: string;
  country_code: string;
  points: RankHistoryPoint[];
}

export interface ComparisonRow {
  institution_id: string;
  institution_name: string;
  country_code?: string | null;
  value: number | null;
  currency?: string | null;
  status: string;
  reason?: string | null;
  data_id?: string | null;
  provenance: ProvenanceRef[];
}

export interface InstitutionsComparison {
  metric_code: string;
  kind: string;
  unit: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: RankingStatus;
  reason?: string | null;
  currency?: string | null;
  rows: ComparisonRow[];
}

export interface SectorComparison {
  metric_code: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: RankingStatus;
  reason?: string | null;
  institution: ComparisonRow | null;
  country_code?: string | null;
  sector_total: number | null;
  sector_currency?: string | null;
  sector_status?: string | null;
  sector_coverage_ratio: number | null;
  sector_institution_count?: number | null;
  sector_total_institutions?: number | null;
  share_percent: number | null;
}

export interface CountryComparison {
  metric_code: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: RankingStatus;
  reason?: string | null;
  country_code: string;
  country_total: number | null;
  country_status?: string | null;
  country_coverage_ratio: number | null;
  umoa_total: number | null;
  umoa_status?: string | null;
  umoa_coverage_ratio: number | null;
  currency?: string | null;
  share_percent: number | null;
}
