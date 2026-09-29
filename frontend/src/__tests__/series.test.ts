/**
 * Test 2 — missing years create a gap (display helpers only).
 *
 * Tests 3–5 of Phase 8C (period_type, scope, rejected / conflict / verified rules)
 * moved to the backend with the qualification itself (Phase 10, single source of
 * rules): backend/tests/test_phase10_institution_profile_unit.py and
 * backend/tests/test_phase10_institution_postgres.py.
 */
import { describe, expect, it } from "vitest";
import { buildYearSeries, toSegments } from "@/lib/series";

// Points as returned by GET /api/v1/institutions/{id}/history (2023 absent).
const points = [
  { period_year: 2020, value: 100, status: "extracted" },
  { period_year: 2021, value: 120, status: "verified" },
  { period_year: 2023, value: 150, status: "extracted" },
];

describe("Test 2 — missing years create a gap", () => {
  it("builds a dense series with an explicit null for the missing year", () => {
    expect(buildYearSeries(points).map(({ year, value }) => ({ year, value }))).toEqual([
      { year: 2020, value: 100 },
      { year: 2021, value: 120 },
      { year: 2022, value: null },
      { year: 2023, value: 150 },
    ]);
  });

  it("never turns the missing year into zero", () => {
    const y2022 = buildYearSeries(points).find((p) => p.year === 2022);
    expect(y2022?.value).toBeNull();
    expect(y2022?.value).not.toBe(0);
    expect(y2022?.status).toBe("unavailable");
  });

  it("splits the line into two segments: 2020–2021 and 2023", () => {
    const segments = toSegments(buildYearSeries(points));
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

  it("no points → no series (nothing invented)", () => {
    expect(buildYearSeries([])).toEqual([]);
  });
});
