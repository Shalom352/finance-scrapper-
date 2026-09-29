/**
 * UMOA Banking Intelligence — Locale-aware Financial Formatters
 *
 * Rules (DATA MISSING > DATA WRONG):
 * - A missing value (null / undefined / NaN) is always rendered as MISSING ("—"),
 *   never as 0, "N/A" or any placeholder number.
 * - Numbers go through Intl for the active locale (fr: "3,45", en: "3.45").
 * - The value and its unit are joined with a non-breaking space.
 * - The XOF currency code is displayed as "FCFA"; stored values are untouched.
 */

export const MISSING = "—";
const NBSP = " ";

export type AppLocale = "fr" | "en";

function intlLocale(locale: string): string {
  return locale === "en" ? "en-US" : "fr-FR";
}

function withUnit(amount: string, unit: string): string {
  return unit ? `${amount}${NBSP}${unit}` : amount;
}

function isMissing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value);
}

/** Display label for a currency code. An unknown currency is not guessed: it returns "". */
export function displayCurrency(currency: string | null | undefined): string {
  if (!currency) return "";
  const code = currency.toUpperCase();
  return code === "XOF" ? "FCFA" : code;
}

export function formatNumber(
  value: number | null | undefined,
  locale: string = "fr",
  decimals: number = 0,
): string {
  if (isMissing(value)) return MISSING;
  return new Intl.NumberFormat(intlLocale(locale), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatCurrency(
  value: number | null | undefined,
  currency: string | null | undefined,
  locale: string = "fr",
  decimals: number = 0,
): string {
  if (isMissing(value)) return MISSING;
  return withUnit(formatNumber(value, locale, decimals), displayCurrency(currency));
}

const COMPACT_UNITS: Record<AppLocale, { billion: string; million: string; thousand: string }> = {
  fr: { billion: "Md", million: "M", thousand: "k" },
  en: { billion: "bn", million: "M", thousand: "k" },
};

export function formatCompactCurrency(
  value: number | null | undefined,
  currency: string | null | undefined,
  locale: string = "fr",
): string {
  if (isMissing(value)) return MISSING;

  const units = COMPACT_UNITS[locale === "en" ? "en" : "fr"];
  const abs = Math.abs(value);
  let scaled: number;
  let unit: string;
  let decimals: number;

  if (abs >= 1e9) {
    scaled = value / 1e9;
    unit = units.billion;
    decimals = 2;
  } else if (abs >= 1e6) {
    scaled = value / 1e6;
    unit = units.million;
    decimals = 2;
  } else if (abs >= 1e3) {
    scaled = value / 1e3;
    unit = units.thousand;
    decimals = 1;
  } else {
    return formatCurrency(value, currency, locale, 0);
  }

  return withUnit(`${formatNumber(scaled, locale, decimals)}${NBSP}${unit}`, displayCurrency(currency));
}

/** `value` is already expressed in percent (12.5 → "12,50 %"). */
export function formatPercent(
  value: number | null | undefined,
  locale: string = "fr",
  decimals: number = 2,
): string {
  if (isMissing(value)) return MISSING;
  const n = formatNumber(value, locale, decimals);
  return locale === "en" ? `${n}%` : `${n}${NBSP}%`;
}

/** Signed percentage for variations: "+3,45 %" / "-1,20 %". */
export function formatSignedPercent(
  value: number | null | undefined,
  locale: string = "fr",
  decimals: number = 2,
): string {
  if (isMissing(value)) return MISSING;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatPercent(value, locale, decimals)}`;
}

/** fr: DD/MM/YYYY — en: MM/DD/YYYY. Invalid or missing dates render as MISSING. */
export function formatDate(dateStr: string | null | undefined, locale: string = "fr"): string {
  if (!dateStr) return MISSING;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return MISSING;
  return new Intl.DateTimeFormat(intlLocale(locale), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

/** Render any optional text/number field, falling back to MISSING. */
export function orMissing(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return MISSING;
  if (typeof value === "number" && Number.isNaN(value)) return MISSING;
  return String(value);
}
