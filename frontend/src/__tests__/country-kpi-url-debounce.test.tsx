/**
 * Test 6 — country KPI mapping; Test 9 — locale switch keeps query params;
 * Test 10 — search debounce.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { resolveKpi, SECTOR_KPI_BINDINGS } from "@/lib/countryKpis";
import { buildLocaleHref, parseYearParam, resolveYear } from "@/lib/url";
import { createDebouncer, useDebouncedValue } from "@/lib/debounce";
import type { SectorAggregation } from "@/types";

function agg(metric_code: string, year = 2023, total_value: number | null = 1000): SectorAggregation {
  return {
    scope: "country",
    country_code: "CI",
    year,
    metric_code,
    total_value,
    currency: "XOF",
    institution_count: 10,
    total_institutions: 12,
    coverage_ratio: 0.83,
    is_partial: true,
    status: "calculated",
    contributing_institutions: [],
  };
}

const deposits = SECTOR_KPI_BINDINGS.find((b) => b.labelKey === "total_deposits")!;
const assets = SECTOR_KPI_BINDINGS.find((b) => b.labelKey === "total_assets")!;

describe("Test 6 — country KPI mapping", () => {
  it("Total Dépôts can never receive a Total Actifs aggregation", () => {
    expect(resolveKpi(deposits, 2023, [agg("total_actifs")])).toBeNull();
  });

  it("each KPI only receives its own metric", () => {
    const all = [agg("total_actifs", 2023, 5000), agg("depots_clients", 2023, 3000)];
    expect(resolveKpi(deposits, 2023, all)?.total_value).toBe(3000);
    expect(resolveKpi(assets, 2023, all)?.total_value).toBe(5000);
  });

  it("an aggregation of another year is rejected", () => {
    expect(resolveKpi(deposits, 2023, [agg("depots_clients", 2022)])).toBeNull();
  });

  it("a failed call (null) resolves to null", () => {
    expect(resolveKpi(deposits, 2023, [null, undefined])).toBeNull();
  });

  it("bindings map deposits to depots_clients and assets to total_actifs", () => {
    expect(deposits.metric_code).toBe("depots_clients");
    expect(assets.metric_code).toBe("total_actifs");
  });
});

describe("Test 9 — locale switch keeps query params", () => {
  it("/search?q=banque&page=2 keeps its query string", () => {
    expect(buildLocaleHref("/search", new URLSearchParams("q=banque&page=2"))).toBe("/search?q=banque&page=2");
  });

  it("keeps filters and selected year", () => {
    const href = buildLocaleHref("/analytics", new URLSearchParams("tab=growth&year=2022&country=SN"));
    expect(href).toBe("/analytics?tab=growth&year=2022&country=SN");
  });

  it("no query → bare path", () => {
    expect(buildLocaleHref("/institutions", new URLSearchParams())).toBe("/institutions");
  });
});

describe("year resolution — never invented", () => {
  it("uses the requested year only if the API has data for it", () => {
    expect(resolveYear(2022, [2023, 2022])).toBe(2022);
    expect(resolveYear(2024, [2023, 2022])).toBe(2023);
  });

  it("no available year → null (no 2024 fallback)", () => {
    expect(resolveYear(null, [])).toBeNull();
    expect(resolveYear(2024, [])).toBeNull();
  });

  it("parses only 4-digit years", () => {
    expect(parseYearParam("2023")).toBe(2023);
    expect(parseYearParam("abc")).toBeNull();
    expect(parseYearParam(undefined)).toBeNull();
  });
});

describe("Test 10 — debounce", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("5 rapid keystrokes → 1 call with the last value", () => {
    const fn = vi.fn();
    const debounced = createDebouncer(fn, 350);
    for (const q of ["b", "ba", "ban", "banq", "banque"]) {
      debounced(q);
      vi.advanceTimersByTime(100);
    }
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(350);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("banque");
  });

  it("cancel prevents the pending call", () => {
    const fn = vi.fn();
    const debounced = createDebouncer(fn, 350);
    debounced("x");
    debounced.cancel();
    vi.advanceTimersByTime(1000);
    expect(fn).not.toHaveBeenCalled();
  });

  it("useDebouncedValue only updates once typing pauses", () => {
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 350), { initialProps: { v: "" } });
    for (const v of ["b", "ba", "ban"]) {
      rerender({ v });
      act(() => {
        vi.advanceTimersByTime(100);
      });
    }
    expect(result.current).toBe("");
    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(result.current).toBe("ban");
  });
});
