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

/** Explorer row (Phase 11): a stored observation, as stored, with its provenance summary. */
export type ObservationQualification =
  | "authoritative"
  | "superseded"
  | "conflict"
  | "needs_review"
  | "rejected"
  | "missing_value";

export interface FinancialDataExplorerItem extends FinancialDataPoint {
  institution_name: string | null;
  country_code: string | null;
  source_id: string | null;
  source_name: string | null;
  document_id: string | null;
  document_title: string | null;
  page_number: number | null;
  qualification: ObservationQualification | null;
  authoritative_data_id: string | null;
}

/** Values really present in the stored observations (explorer filters). */
export interface FinancialDataFacets {
  period_years: number[];
  period_types: string[];
  scopes: string[];
  currencies: string[];
  statuses: string[];
  metric_codes: string[];
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

// ============================================================
// Data Quality & Review Center (Phase 12)
// ============================================================

export type ReviewAction = "review" | "verify" | "reject";
/** Every action recorded in the audit journal (human decisions + deal import / duplicate decisions). */
export type ReviewEventAction =
  | ReviewAction
  | "import"
  | "mark_same_deal"
  | "mark_distinct"
  | "mark_same_deal_multi_source";

/** Plain counts of stored observations (backend `DataQualityCounts`). */
export interface ReviewCenterCounts {
  total: number;
  extracted: number;
  needs_review: number;
  reviewed: number;
  verified: number;
  rejected: number;
  conflict_keys: number;
  conflict_observations: number;
  unresolved: number;
  /** Deals (Phase 13): not attached to another deal; open duplicate candidates. */
  deals_total?: number;
  deals_needs_review?: number;
  deals_reviewed?: number;
  deals_verified?: number;
  deals_rejected?: number;
  deals_duplicate_candidates?: number;
}

export type DifferenceReason = "same_observation" | "missing_value" | "currency_mismatch" | "unit_mismatch";

export interface ReviewObservation {
  id: string;
  status: string;
  qualification: ObservationQualification | null;
  scope: string;
  period_type: string;
  period_year: number;
  value_original: string;
  value_normalized: number | null;
  unit_normalized: string | null;
  currency_normalized: string | null;
  extraction_method: string;
  source_name: string | null;
  document_title: string | null;
  page_number: number | null;
  /** other − observation under review; only for the same currency and unit. */
  difference: number | null;
  difference_reason: DifferenceReason | null;
}

export interface ReviewDetail {
  observation: FinancialDataDetail;
  country_code: string | null;
  qualification: ObservationQualification | null;
  authoritative_data_id: string | null;
  allowed_actions: ReviewAction[];
  competing: ReviewObservation[];
  not_comparable: ReviewObservation[];
}

/** One audit event: targets an observation OR a deal (single journal, Phase 13). */
export interface ReviewEvent {
  id: string;
  financial_data_id: string | null;
  deal_id?: string | null;
  deal_duplicate_candidate_id?: string | null;
  action: ReviewEventAction;
  previous_status: string;
  new_status: string;
  reason: string | null;
  actor: string | null;
  value_before: number | null;
  value_after: number | null;
  created_at: string;
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
  status: "ok" | "unavailable";
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

// ============================================================
// Phase 10 — Institution financial profile (backend-qualified)
// ============================================================

export type ProfileStatus = "available" | "partial" | "needs_review" | "unavailable";

export interface ProfileSelection {
  scopes: string[];
  period_types: string[];
  years: number[];
}

/** One authoritative value qualified by the backend, with its full provenance. */
export interface ProfileValue {
  metric_code: string;
  period_year: number;
  period_type: string;
  period_label?: string | null;
  data_scope: string;
  value_original: string;
  unit_original?: string | null;
  currency_original?: string | null;
  value_normalized: number | null;
  unit_normalized?: string | null;
  currency?: string | null;
  status: string;
  data_id: string;
  provenance: ProvenanceRef;
}

export interface UnavailableValue {
  metric_code: string;
  period_year?: number | null;
  status: string;
  reason: string;
}

export interface InstitutionFinancials {
  institution_id: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: ProfileStatus;
  reason?: string | null;
  selection: ProfileSelection;
  values: ProfileValue[];
  unavailable: UnavailableValue[];
}

export interface HistoryPoint {
  period_year: number;
  value: number | null;
  currency?: string | null;
  unit_normalized?: string | null;
  status: string;
  data_id: string;
  provenance: ProvenanceRef;
}

export interface HistorySeries {
  metric_code: string;
  status: ProfileStatus;
  reason?: string | null;
  currency?: string | null;
  points: HistoryPoint[];
  missing_years: number[];
  excluded_years: UnavailableValue[];
}

export interface InstitutionHistory {
  institution_id: string;
  period_type: string;
  data_scope: string;
  status: ProfileStatus;
  reason?: string | null;
  selection: ProfileSelection;
  series: HistorySeries[];
}

export interface DataQualityCounts {
  total_observations: number;
  verified: number;
  reviewed: number;
  extracted: number;
  needs_review: number;
  rejected: number;
  conflicts: number;
  missing_years: number;
}

export interface SourceDocument {
  document_id: string;
  title?: string | null;
  source_name?: string | null;
  period_years: number[];
  pages: number[];
  values_count: number;
}

export interface InstitutionProfileCoverage {
  institution_id: string;
  period_type: string;
  data_scope: string;
  status: ProfileStatus;
  reason?: string | null;
  first_year: number | null;
  last_year: number | null;
  available_years: number[];
  missing_years: number[];
  available_years_count: number;
  /** Every year between first_year and last_year; null without data (never 0/1). */
  expected_years_count: number | null;
  coverage_ratio: number | null;
  quality: DataQualityCounts;
  documents: SourceDocument[];
}

export interface InstitutionRatios {
  institution_id: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: ProfileStatus;
  reason?: string | null;
  items: RatioResult[];
}

export interface InstitutionGrowth {
  institution_id: string;
  period_year: number | null;
  period_type: string;
  data_scope: string;
  status: ProfileStatus;
  reason?: string | null;
  items: GrowthResult[];
}

// ============================================================
// Phase 13 — Deal Intelligence (structured import only; NULL stays null)
// ============================================================

export type DealStatus = "extracted" | "needs_review" | "reviewed" | "verified" | "rejected";
export type DealDuplicateState = "duplicate_candidate" | "same_deal" | "distinct_deals" | "same_deal_multi_source";
export type DuplicateDecision = "same_deal" | "distinct_deals" | "same_deal_multi_source";

export const DEAL_TYPES = [
  "term_loan",
  "syndicated_loan",
  "project_finance",
  "trade_finance",
  "bond",
  "guarantee",
  "equity",
  "ipo",
  "sovereign_bond",
  "corporate_bond",
  "sukuk",
  "blended_finance",
  "m_and_a",
  "other",
  "sovereign_bond_ape",
  "corporate_bond_ape",
  "corporate_bond_private",
  "debt_buyback",
  "debt_exchange",
  "debt_reprofiling",
  "securitisation",
  "capital_increase",
  "share_sale_public",
  "takeover_offer",
] as const;
export const PARTICIPANT_ROLES = [
  "borrower",
  "lender",
  "arranger",
  "co_arranger",
  "agent",
  "guarantor",
  "sponsor",
  "advisor",
  "investor",
  "insurer",
  "reinsurer",
  "issuer",
  "underwriter",
  "trustee",
  "facility_agent",
  "security_agent",
  "lead_manager",
  "co_lead_manager",
  "placement_syndicate_member",
  "financial_advisor",
  "anchor_investor",
  "refinanced_lender",
  "selling_shareholder",
  "paying_agent",
] as const;
export const DEAL_STATUSES: DealStatus[] = ["extracted", "needs_review", "reviewed", "verified", "rejected"];

export interface DealParticipant {
  id: string;
  participant_name: string;
  institution_id: string | null;
  institution_name: string | null;
  entity_id?: string | null;
  entity_name?: string | null;
  role: string;
  commitment_amount: number | null;
  commitment_currency: string | null;
  deal_source_id: string;
  /** Where the role is named (Phase 19). */
  page_number?: number | null;
  excerpt?: string | null;
  extraction_method?: "text" | "visual_logo" | "visual_scan" | null;
}

export interface DealSource {
  id: string;
  deal_id: string;
  document_id: string;
  document_title: string | null;
  document_url: string | null;
  source_id: string;
  source_name: string | null;
  page_number: number;
  excerpt: string | null;
  fields: string[];
  /** Confidence class (Phase 19); null for sources recorded before. */
  source_class?: string | null;
  publisher?: string | null;
  title?: string | null;
  url?: string | null;
  published_at?: string | null;
  paywalled?: boolean | null;
}

export interface DealDuplicate {
  id: string;
  other_deal_id: string;
  other_deal_title: string | null;
  other_deal_status: string | null;
  matched_criteria: string[];
  state: DealDuplicateState;
  primary_deal_id: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_reason: string | null;
}

export interface DealListItem {
  id: string;
  title: string;
  deal_type: string | null;
  status: DealStatus;
  country_code: string | null;
  sector: string | null;
  project_name: string | null;
  amount: number | null;
  currency: string | null;
  unit: string | null;
  announcement_date: string | null;
  signing_date: string | null;
  borrowers: string[];
  arrangers: string[];
  issuers?: string[];
  instrument_type?: string | null;
  isin?: string | null;
  value_date?: string | null;
  duplicate_candidates: number;
  merged_into_deal_id: string | null;
  updated_at: string;
}

export interface MergedDeal {
  id: string;
  title: string;
  status: DealStatus;
  sources: DealSource[];
  participants: DealParticipant[];
}

export interface DealDetail extends DealListItem {
  amount_original: string | null;
  interest_rate: number | null;
  interest_rate_type: string | null;
  benchmark: string | null;
  spread_bps: number | null;
  maturity_months: number | null;
  grace_period_months: number | null;
  fees: string | null;
  guarantees: string | null;
  financial_close_date: string | null;
  closing_date: string | null;
  auction_reference?: string | null;
  auction_date?: string | null;
  maturity_date?: string | null;
  yield_rate?: number | null;
  validation_flags?: { code: string; detail: string }[];
  /** Quoted use of proceeds and closed categories (Phase 19). */
  use_of_proceeds?: string | null;
  use_of_proceeds_categories?: string[];
  /** Raw "SGI déclarante" of the AMF API — never a role. */
  filing_agent_raw?: string | null;
  notes: string | null;
  verified_at: string | null;
  verified_by: string | null;
  created_at: string;
  participants: DealParticipant[];
  sources: DealSource[];
  field_provenance: Record<string, string[]>;
  duplicates: DealDuplicate[];
  merged_deals: MergedDeal[];
  allowed_actions: ReviewAction[];
}

export interface DealCurrencyTotal {
  currency: string;
  unit: string | null;
  total: number | null;
  deals: number;
}

export interface DealAnalyticsRow {
  key: string | null;
  label: string | null;
  deals: number;
  by_status: Record<string, number>;
  amounts: DealCurrencyTotal[];
  deals_without_amount: number;
}

export type DealDimension = "country" | "year" | "type" | "sector" | "institution";

export interface DealAnalytics {
  dimension: DealDimension;
  rows: DealAnalyticsRow[];
  amount_basis: string;
}

// ============================================================
// Automated Ingestion
// ============================================================

export type IngestionStatus = "running" | "completed" | "partial_failure" | "failed" | "skipped_concurrent";
export type IngestionTrigger = "scheduled" | "manual" | "cli";

export interface IngestionRun {
  id: string;
  trigger_type: IngestionTrigger;
  status: IngestionStatus;
  target_years: string | null;
  sources_checked: number;
  documents_found: number;
  documents_new: number;
  documents_downloaded: number;
  documents_skipped: number;
  documents_failed: number;
  data_points_extracted: number;
  data_points_needing_review: number;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  errors: Array<{ source?: string; phase?: string; error: string }> | null;
  summary_text: string | null;
  created_at: string;
}

