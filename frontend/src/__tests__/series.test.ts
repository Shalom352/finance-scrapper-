/**
 * Tests 2–5 — missing years, period_type, scope and rejected handling.
 */
import { describe, expect, it } from "vitest";
import { buildYearSeries, findObservation, latestYear, qualifyObservations, toSegments } from "@/lib/series";
import { point } from "./helpers";

const ANNUAL_INDIVIDUAL = { periodType: "annual", scope: "individual" };

describe("Test 2 — missing years create a gap", () => {
  const qualified = qualifyObservations(
    [
      point({ period_year: 2020, value_normalized: 100 }),
      point({ period_year: 2021, value_normalized: 120 }),
      point({ period_year: 2023, value_normalized: 150 }),
    ],
    ANNUAL_INDIVIDUAL,
  );

  it("builds a dense series with an explicit null for 2022", () => {
    expect(buildYearSeries(qualified, "total_actifs").map(({ year, value }) => ({ year, value }))).toEqual([
      { year: 2020, value: 100 },
      { year: 2021, value: 120 },
      { year: 2022, value: null },
      { year: 2023, value: 150 },
    ]);
  });

  it("never turns the missing year into zero", () => {
    const y2022 = buildYearSeries(qualified, "total_actifs").find((p) => p.year === 2022);
    expect(y2022?.value).toBeNull();
    expect(y2022?.value).not.toBe(0);
  });

  it("splits the line into two segments: 2020–2021 and 2023", () => {
    const segments = toSegments(buildYearSeries(qualified, "total_actifs"));
    expect(segments.map((s) => s.map((p) => p.year))).toEqual([[2020, 2021], [2023]]);
  });

  it("also breaks a sparse series (caller omitted the missing year)", () => {
    const segments = toSegments([
      { year: 2020, value: 1 },
      { year: 2021, value: 2 },
      { year: 2023, value: 3 },
    ]);
    expect(segments).toHaveLength(2);
  });
});

describe("Test 3 — period_type is never mixed", () => {
  it("an annual series excludes semi-annual data", () => {
    const qualified = qualifyObservations(
      [
        point({ period_year: 2023, value_normalized: 100, period_type: "annual" }),
        point({ period_year: 2023, value_normalized: 55, period_type: "semi_annual" }),
        point({ period_year: 2022, value_normalized: 40, period_type: "semi_annual" }),
      ],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified).toHaveLength(1);
    expect(qualified[0]).toMatchObject({ period_year: 2023, value: 100, conflict: false });
  });
});

describe("Test 4 — scope is never mixed", () => {
  it("an individual series excludes consolidated data", () => {
    const qualified = qualifyObservations(
      [
        point({ period_year: 2023, value_normalized: 100, scope: "individual" }),
        point({ period_year: 2023, value_normalized: 900, scope: "consolidated" }),
      ],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified).toHaveLength(1);
    expect(qualified[0].value).toBe(100);
  });
});

describe("Test 5 — rejected data is never displayed as valid", () => {
  it("drops rejected observations", () => {
    const qualified = qualifyObservations(
      [point({ period_year: 2023, value_normalized: 999, status: "rejected" })],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified).toEqual([]);
    expect(findObservation(qualified, "total_actifs", 2023)).toBeUndefined();
  });

  it("a rejected value never wins over a valid one", () => {
    const qualified = qualifyObservations(
      [
        point({ period_year: 2023, value_normalized: 999, status: "rejected" }),
        point({ period_year: 2023, value_normalized: 100, status: "extracted" }),
      ],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified[0]).toMatchObject({ value: 100, status: "extracted", conflict: false });
  });

  it("verified wins over other statuses", () => {
    const qualified = qualifyObservations(
      [
        point({ period_year: 2023, value_normalized: 100, status: "extracted" }),
        point({ id: "v", period_year: 2023, value_normalized: 120, status: "verified" }),
      ],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified[0]).toMatchObject({ value: 120, status: "verified", data_id: "v" });
  });

  it("divergent unverified values are a conflict: value null, never an arbitrary pick", () => {
    const qualified = qualifyObservations(
      [
        point({ period_year: 2023, value_normalized: 100, status: "extracted" }),
        point({ period_year: 2023, value_normalized: 130, status: "reviewed" }),
      ],
      ANNUAL_INDIVIDUAL,
    );
    expect(qualified[0]).toMatchObject({ value: null, conflict: true, data_id: null });
  });

  it("null values are ignored, not treated as zero", () => {
    const qualified = qualifyObservations([point({ value_normalized: null })], ANNUAL_INDIVIDUAL);
    expect(qualified).toEqual([]);
    expect(latestYear(qualified)).toBeNull();
  });
});
