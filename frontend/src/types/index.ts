/**
 * UMOA Banking Intelligence — TypeScript Types
 *
 * Shared types used across the frontend application.
 * Mirrors the backend Pydantic schemas (v1 + analytics).
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

// ============================================================
// UMOA Geography
// ============================================================

export type UMOACountryCode = "BJ" | "BF" | "CI" | "GW" | "ML" | "NE" | "SN" | "TG";

export interface Country {
  id: string;
  iso_code_2?: string;
  code?: UMOACountryCode;
  name_fr: string;
  name_en: string;
  capital_fr?: string;
  capital_en?: string;
  flag_emoji?: string;
  is_active: boolean;
  institutions_count?: number;
}

// ============================================================
// Sources
// ============================================================

export interface Source {
  id: string;
  name: string;
  short_name?: string;
  publisher?: string;
  url?: string;
  source_type: "regulatory" | "central_bank" | "bank" | "banking_group" | "government" | "financial_market" | "secondary";
  priority: number;
  country_code?: string;
  language?: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SourceList {
  id: string;
  name: string;
  short_name?: string;
  source_type: string;
  priority: number;
  country_code?: string;
  is_active: boolean;
}

// ============================================================
// Institutions
// ============================================================

export interface BankingGroupList {
  id: string;
  name: string;
  short_name?: string;
  headquarter_country_code?: string;
}

export interface Institution {
  id: string;
  name_official?: string;
  name?: string;
  name_commercial?: string;
  institution_type: string;
  country_id: string;
  country?: Country;
  banking_group_id?: string;
  banking_group?: BankingGroupList;
  regulatory_id?: string;
  website_url?: string;
  status: "active" | "closed" | "in_liquidation" | "merged" | "unknown";
  description?: string;
  data_notes?: string;
  source_id?: string;
  source?: SourceList;
  created_at: string;
  updated_at: string;
  data_count?: number;
  latest_year?: number;
}

// ============================================================
// Documents
// ============================================================

export type DocumentType =
  | "annual_report"
  | "financial_statement"
  | "regulatory_report"
  | "press_release"
  | "web_page"
  | "other";

export interface Document {
  id: string;
  title: string;
  document_type: DocumentType;
  institution_id?: string;
  institution?: Institution;
  source_id: string;
  source?: Source;
  url?: string;
  file_hash?: string;
  file_size?: number;
  storage_path?: string;
  download_status: "pending" | "downloaded" | "failed";
  page_count?: number;
  extraction_status: "pending" | "extracted" | "failed" | "skipped";
  extracted_at?: string;
  published_at?: string;
  period_year?: number;
  period_type?: "annual" | "semi_annual" | "quarterly";
  language?: string;
  collected_at?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Financial Data
// ============================================================

export type ExtractionMethod = "pdf_table" | "pdf_text" | "ocr" | "web_html" | "manual";

export interface FinancialDataPoint {
  id: string;
  institution_id: string;
  institution?: Institution;
  source_id: string;
  source?: Source;
  document_id: string;
  document?: Document;
  metric_code: string;
  scope: "individual" | "consolidated";
  period_type: "annual" | "semi_annual" | "quarterly";
  period_year: number;
  period_label?: string;

  // Raw extracted value
  value_original: string;
  unit_original?: string;
  currency_original?: string;

  // Normalized value
  value_normalized?: number;
  unit_normalized?: string;
  currency_normalized?: string;

  // Provenance
  page_number?: number;
  extraction_method: ExtractionMethod;
  confidence_score?: number;
  status: DataStatus;

  notes?: string;
  extracted_at?: string;
  verified_at?: string;
  verified_by?: string;
  created_at: string;
  updated_at: string;
}

export interface MetricDefinition {
  id?: string;
  code: string;
  label_fr: string;
  label_en: string;
  definition_fr: string;
  definition_en: string;
  statement_type: string;
  category: string;
  value_type: "amount" | "percentage" | "ratio" | "rate";
  currency_type: "monetary" | "non_monetary";
  is_calculated: boolean;
  is_active: boolean;
  is_debt_related: boolean;
  display_order: number;
  description_synth?: string;
}

// ============================================================
// Phase 7 Analytics & Ratios
// ============================================================

export interface ComponentProvenance {
  data_id: string;
  metric_code: string;
  period_year: number;
  period_type: string;
  value_normalized?: number;
  currency?: string;
  source_id?: string;
  source_name?: string;
  document_id?: string;
  page_number?: number;
  status: string;
  role?: string;
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
  institution_name?: string;
  country_code?: string;
  period_year: number;
  period_type: string;
  value?: number;
  value_percent?: number;
  unit: string;
  status: RatioStatus;
  reason?: string;
  formula_used: string;
  components: ComponentProvenance[];
  calculated_at: string;
}

export interface GrowthResult {
  metric_code: string;
  metric_label?: string;
  institution_id: string;
  institution_name?: string;
  country_code?: string;
  current_year: number;
  previous_year: number;
  current_value?: number;
  previous_value?: number;
  absolute_change?: number;
  growth_rate?: number;
  growth_percent?: number;
  currency?: string;
  status: string;
  reason?: string;
  components: ComponentProvenance[];
  calculated_at: string;
}

export interface SectorAggregation {
  scope: "country" | "umoa";
  country_code?: string;
  country_name?: string;
  year: number;
  metric_code: string;
  metric_label?: string;
  total_value?: number;
  currency: string;
  institution_count: number;
  total_institutions: number;
  coverage_ratio: number;
  is_partial: boolean;
  status: string;
  contributing_institutions: string[];
  notes?: string;
}

export interface MarketShare {
  institution_id: string;
  institution_name?: string;
  country_code: string;
  year: number;
  metric_code: string;
  institution_value: number;
  sector_total_value: number;
  market_share: number;
  market_share_percent: number;
  currency: string;
  coverage_ratio: number;
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
  value_a?: number;
  value_b?: number;
  unit?: string;
  difference?: number;
  ratio_a_to_b?: number;
  description: string;
}

// ============================================================
// Search & API Responses
// ============================================================

export interface SearchResults {
  query: string;
  total: number;
  institutions: Institution[];
  banking_groups: BankingGroupList[];
  sources: Source[];
  documents: Document[];
  metrics?: MetricDefinition[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  env: string;
  timestamp: string;
  database?: {
    status: "ok" | "error";
    host: string;
    port: number;
    db: string;
    error?: string;
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}
