/** Phase 20 — targeting URL state. Invalid values are dropped, never guessed. */
import type { TargetingQuery } from "@/types";
import { DEAL_TYPES, SECTORS } from "@/types";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";

export const CURRENCIES = ["XOF", "EUR", "USD"] as const;
export const KINDS = ["all", "banks", "institutions"] as const;

const oneOf = <T extends string>(values: readonly T[], v: string): T | undefined =>
  (values as readonly string[]).includes(v) ? (v as T) : undefined;

/** URL -> query: invalid values are dropped, never guessed. */
export function parseTargetingParams(get: (k: string) => string): TargetingQuery {
  const amount = Number(get("amount"));
  return {
    country: oneOf(UMOA_COUNTRY_CODES, get("country")),
    sector: oneOf(SECTORS, get("sector")),
    deal_type: oneOf(DEAL_TYPES, get("deal_type")),
    amount: Number.isFinite(amount) && amount > 0 ? amount : undefined,
    currency: oneOf(CURRENCIES, get("currency")),
    kind: oneOf(KINDS, get("kind")),
  };
}

