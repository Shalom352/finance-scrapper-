/**
 * Test 8 — country code contract (`code`, never `iso_code_2`).
 * Plus: no fabricated fallbacks in UI source, Decimal-string normalization,
 * and FR/EN dictionary parity.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { toNumberOrNull } from "@/lib/api";
import fr from "@/messages/fr.json";
import en from "@/messages/en.json";

const SRC = join(__dirname, "..");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "__tests__" ? [] : sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

const files = sourceFiles(SRC).map((f) => ({ path: f.slice(SRC.length), text: readFileSync(f, "utf8") }));

describe("Test 8 — country code contract", () => {
  it("no source file references iso_code_2", () => {
    expect(files.filter((f) => f.text.includes("iso_code_2")).map((f) => f.path)).toEqual([]);
  });

  it("the Country type exposes `code`", () => {
    const types = files.find((f) => /types[\\/]index\.ts$/.test(f.path))!;
    expect(types.text).toMatch(/export interface Country \{[^}]*\bcode: string;/);
  });
});

describe("no fabricated fallbacks in UI code", () => {
  const ui = files.filter((f) => /[\\/](app|components)[\\/]/.test(f.path));
  const forbidden: [string, RegExp][] = [
    ["coverage fallback 0.85", /0\.85/],
    ["hard-coded fiscal year 2024/2023", /\b202[34]\b/],
    ["large literal amount", /\b\d{10,}\b/],
    ['"N/A" placeholder', /N\/A/],
    ['"140+" style placeholder', /"\d[\d\s]*\+"/],
    ["|| 0 on a value", /\|\|\s*0(?![.\d])/],
    ["?? 0 on a value", /\?\?\s*0(?![.\d])/],
  ];

  for (const [label, re] of forbidden) {
    it(`no ${label}`, () => {
      expect(ui.filter((f) => re.test(f.text)).map((f) => f.path)).toEqual([]);
    });
  }
});

describe("Decimal normalization", () => {
  it("Pydantic Decimal strings become numbers; missing stays null", () => {
    expect(toNumberOrNull("3450000.00")).toBe(3450000);
    expect(toNumberOrNull(12.5)).toBe(12.5);
    expect(toNumberOrNull("0")).toBe(0);
    expect(toNumberOrNull(null)).toBeNull();
    expect(toNumberOrNull(undefined)).toBeNull();
    expect(toNumberOrNull("")).toBeNull();
    expect(toNumberOrNull("abc")).toBeNull();
  });
});

describe("i18n parity", () => {
  function keys(obj: Record<string, unknown>, prefix = ""): string[] {
    return Object.entries(obj).flatMap(([k, v]) =>
      v && typeof v === "object" ? keys(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`],
    );
  }

  it("fr.json and en.json have exactly the same keys", () => {
    expect(keys(en).sort()).toEqual(keys(fr).sort());
  });
});
