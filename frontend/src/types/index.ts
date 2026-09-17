/**
 * UMOA Banking Intelligence — TypeScript Types
 *
 * Shared types used across the frontend application.
 * These mirror the backend Pydantic schemas.
 */

// ============================================================
// Common
// ============================================================

export type Locale = "fr" | "en";

export type DataStatus =
  | "extracted"
  | "needs_review"
  | "reviewed"
  | "verified"
  | "rejected";

// ============================================================
// UMOA Geography
// ============================================================

export type UMOACountryCode = "BJ" | "BF" | "CI" | "GW" | "ML" | "NE" | "SN" | "TG";

export interface Country {
  id: string;
  code: UMOACountryCode;
  name_fr: string;
  name_en: string;
  capital_fr: string;
  capital_en: string;
  flag_emoji: string;
}

// ============================================================
// Institutions (Phase 1)
// ============================================================

export interface Institution {
  id: string;
  name: string;
  country_id: string;
  country?: Country;
  banking_group_id?: string;
  status: "active" | "closed" | "in_liquidation" | "merged";
  source_url?: string;
  source_id?: string;
  collected_at?: string;
  created_at: string;
  updated_at: string;
}

// ============================================================
// Sources
// ============================================================

export interface Source {
  id: string;
  name: string;
  url: string;
  type: "regulatory" | "bank" | "group" | "secondary";
  priority: 1 | 2 | 3;
  language: "fr" | "en" | "pt";
}

// ============================================================
// Documents (Phase 2)
// ============================================================

export type DocumentType =
  | "annual_report"
  | "financial_statement"
  | "regulatory_report"
  | "press_release"
  | "other";

export interface Document {
  id: string;
  title: string;
  document_type: DocumentType;
  institution_id?: string;
  source_id: string;
  url: string;
  file_hash?: string;
  period_year?: number;
  language: string;
  download_status: "pending" | "downloaded" | "failed";
  created_at: string;
}

// ============================================================
// Financial Data (Phase 3)
// ============================================================

export type ExtractionMethod = "pdf_table" | "pdf_text" | "ocr" | "manual";

export interface FinancialDataPoint {
  id: string;
  institution_id: string;
  metric_code: string;
  period_year: number;
  period_type: "annual" | "semi_annual" | "quarterly";

  // Raw extracted value — never modified after extraction
  value_original: string;
  unit_original: string;

  // Normalized value — for comparison and display
  value_normalized?: number;
  unit_normalized?: string;

  // Provenance — mandatory for all financial data
  source_id: string;
  document_id: string;
  page_number: number;

  extraction_method: ExtractionMethod;
  confidence_score?: number;
  status: DataStatus;

  notes?: string;
  extracted_at: string;
  verified_at?: string;
  verified_by?: string;
}

// ============================================================
// API Responses
// ============================================================

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
