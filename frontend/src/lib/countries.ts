/**
 * Reference list of the 8 UMOA member states (geography, not financial data).
 * Names are translated through `country_names.*` in the message dictionaries.
 */

export const UMOA_COUNTRY_CODES = ["BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"] as const;

export type UmoaCountryCode = (typeof UMOA_COUNTRY_CODES)[number];

export const COUNTRY_FLAGS: Record<string, string> = {
  BJ: "🇧🇯",
  BF: "🇧🇫",
  CI: "🇨🇮",
  GW: "🇬🇼",
  ML: "🇲🇱",
  NE: "🇳🇪",
  SN: "🇸🇳",
  TG: "🇹🇬",
};

export function isUmoaCountry(code: string): code is UmoaCountryCode {
  return (UMOA_COUNTRY_CODES as readonly string[]).includes(code);
}
