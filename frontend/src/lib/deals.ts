/**
 * Deal Intelligence (Phase 13) — URL state and display helpers.
 *
 * Filters live in the URL (reload / locale switch keep them). Nothing is inferred:
 * a missing value stays MISSING, amounts are never converted nor added across currencies.
 */
import type { DealQuery } from "@/lib/api";
import { DEAL_STATUSES, DEAL_TYPES, PARTICIPANT_ROLES } from "@/types";
import { MISSING } from "@/lib/formatters";

export const DEAL_PAGE_SIZE = 20;

/** Currencies offered by the filter (any ISO code in the URL is still honoured). */
export const DEAL_CURRENCIES = ["XOF", "EUR", "USD", "XAF", "GBP"] as const;

export const DEAL_FILTER_KEYS = [
  "country",
  "bank",
  "deal_type",
  "sector",
  "year",
  "currency",
  "status",
  "participant_role",
  "borrower",
  "arranger",
  "include_merged",
] as const;

const oneOf = <T extends string>(values: readonly T[], v: string): T | undefined =>
  (values as readonly string[]).includes(v) ? (v as T) : undefined;

export function parseDealParams(get: (key: string) => string): { query: DealQuery; page: number } {
  const year = Number.parseInt(get("year"), 10);
  const page = Number.parseInt(get("page"), 10);
  const text = (k: string) => get(k).trim() || undefined;
  const country = get("country");
  const currency = get("currency");
  return {
    query: {
      country: /^[A-Z]{2}$/.test(country) ? country : undefined,
      bank: text("bank"),
      deal_type: oneOf(DEAL_TYPES, get("deal_type")),
      sector: text("sector"),
      year: Number.isInteger(year) && year >= 1900 && year <= 2100 ? year : undefined,
      currency: /^[A-Z]{3}$/.test(currency) ? currency : undefined,
      status: oneOf(DEAL_STATUSES, get("status")),
      participant_role: oneOf(PARTICIPANT_ROLES, get("participant_role")),
      borrower: text("borrower"),
      arranger: text("arranger"),
      include_merged: get("include_merged") === "true" ? true : undefined,
    },
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

/**
 * A calendar date ("2024-03-15") rendered without any time-zone shift
 * (new Date("2024-03-15") is UTC midnight and can move one day back in local time).
 */
export function formatDay(value: string | null | undefined, locale: string): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return MISSING;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (Number.isNaN(date.getTime())) return MISSING;
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : "fr-FR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

/** Signing date, otherwise announcement date (same rule as the backend year filter). */
export function dealDate(d: { signing_date: string | null; announcement_date: string | null }): string | null {
  return d.signing_date ?? d.announcement_date ?? null;
}
