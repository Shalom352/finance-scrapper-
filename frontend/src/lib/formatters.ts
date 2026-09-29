/**
 * UMOA Banking Intelligence — Centralized Financial Formatters
 *
 * Ensures uniform formatting across all views and languages:
 * - Currency amounts (standard and compact: M, Md)
 * - Percentages and financial ratios
 * - Dates and coverage ratios
 */

export function formatCurrency(
  value: number | null | undefined,
  currency: string = "XOF",
  decimals: number = 0,
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

  return `${formatted} ${currency}`;
}

export function formatCompactCurrency(
  value: number | null | undefined,
  currency: string = "XOF",
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  const absVal = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  // Billions (Milliards)
  if (absVal >= 1_000_000_000) {
    const formatted = (absVal / 1_000_000_000).toFixed(2);
    return `${sign}${formatted} Md ${currency}`;
  }

  // Millions
  if (absVal >= 1_000_000) {
    const formatted = (absVal / 1_000_000).toFixed(2);
    return `${sign}${formatted} M ${currency}`;
  }

  // Thousands
  if (absVal >= 1_000) {
    const formatted = (absVal / 1_000).toFixed(1);
    return `${sign}${formatted} k ${currency}`;
  }

  return formatCurrency(value, currency, 0);
}

export function formatPercent(
  value: number | null | undefined,
  decimals: number = 2,
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  const formatted = new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

  return `${formatted} %`;
}

export function formatRatio(
  valuePercent: number | null | undefined,
): string {
  if (valuePercent === null || valuePercent === undefined || isNaN(valuePercent)) {
    return "N/A";
  }

  return formatPercent(valuePercent, 2);
}

export function formatNumber(
  value: number | null | undefined,
  decimals: number = 0,
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "—";
  }

  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatDate(
  dateStr: string | null | undefined,
  locale: string = "fr",
): string {
  if (!dateStr) return "—";

  try {
    const d = new Date(dateStr);
    return new Intl.DateTimeFormat(locale === "en" ? "en-US" : "fr-FR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(d);
  } catch {
    return dateStr;
  }
}
