/**
 * Phase 9 — rankings & comparisons UI: rendering, ties, missing values, coverage,
 * filters / URL parameters, pagination, locale, provenance, unavailable section.
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ComparisonRow, InstitutionsComparison, RankHistory, RankingEntry, RankingUnavailableEntry } from "@/types";
import { MISSING } from "@/lib/formatters";
import { buildLocaleHref } from "@/lib/url";
import { DEFAULT_INDICATOR, UMOA, parseIds, parseRankingParams, supportsPeriodType } from "@/lib/rankings";
import { renderWithIntl } from "./helpers";

// Plain functions (no vi.fn spy on rejected promises), see provenance-chart.test.tsx.
const api = vi.hoisted(() => ({ calls: [] as string[] }));
vi.mock("@/lib/api", () => ({
  getFinancialDataById: (id: string) => {
    api.calls.push(id);
    return new Promise(() => {}); // stays loading: the call itself is what we assert
  },
  // Backend catalogue shape (RATIO_DEFINITIONS name_fr / name_en).
  getRatioDefinitions: () =>
    Promise.resolve([
      { ratio_code: "DEPOTS_ACTIFS", name_fr: "Ratio dépôts sur actifs", name_en: "Deposits to Assets Ratio" },
      { ratio_code: "ROA", name_fr: "Rentabilité des actifs (ROA)", name_en: "Return on Assets (ROA)" },
    ]),
}));
vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { RankHistoryTable, RankingTable, UnavailableList } from "@/components/rankings/RankingTable";
import { ComparisonTable, differenceFromReference } from "@/components/rankings/ComparisonTable";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { CountryComparisonCard, SectorComparisonCard } from "@/components/rankings/ComparisonTable";
import { useIndicatorLabel } from "@/components/rankings/IndicatorSelect";
import { resetRatioDefinitionsCache } from "@/lib/useRatioDefinitions";
import type { CountryComparison, SectorComparison } from "@/types";
import { Pagination } from "@/components/common/Pagination";

const NBSP = " ";

function entry(rank: number, id: string, value: number, extra: Partial<RankingEntry> = {}): RankingEntry {
  return {
    rank,
    institution_id: id,
    institution_name: `Banque ${id}`,
    country_code: "CI",
    metric_code: "total_actifs",
    period_year: 2024,
    period_type: "annual",
    data_scope: "individual",
    value,
    unit: "XOF",
    currency: "XOF",
    status: "verified",
    data_id: `fd-${id}`,
    provenance: [],
    ...extra,
  };
}

describe("ranking table", () => {
  it("renders shared ranks for ties (1, 1, 3)", () => {
    renderWithIntl(
      <RankingTable
        items={[entry(1, "A", 5e9), entry(1, "B", 5e9), entry(3, "C", 3e9)]}
        onProvenance={() => {}}
      />,
    );
    expect(screen.getAllByTestId("rank-cell").map((c) => c.textContent)).toEqual(["1", "1", "3"]);
    expect(screen.getAllByTestId("value-cell")[0].textContent).toBe(`5,00${NBSP}Md${NBSP}FCFA`);
  });

  it("formats ratio / growth values as percentages", () => {
    renderWithIntl(<RankingTable items={[entry(1, "A", 12.5, { unit: "%", currency: null })]} onProvenance={() => {}} />);
    expect(screen.getByTestId("value-cell").textContent).toBe(`12,50${NBSP}%`);
  });

  it("provenance button hands the entry (with its data_id) to the panel", () => {
    const onProvenance = vi.fn();
    renderWithIntl(<RankingTable items={[entry(1, "A", 1)]} onProvenance={onProvenance} />);
    fireEvent.click(screen.getByTestId("provenance-button"));
    expect(onProvenance).toHaveBeenCalledWith(expect.objectContaining({ data_id: "fd-A" }));
  });

  it("English locale labels", () => {
    renderWithIntl(<RankingTable items={[entry(1, "A", 1)]} onProvenance={() => {}} />, "en");
    expect(screen.getByText("Rank")).toBeTruthy();
    expect(screen.getByText("Provenance")).toBeTruthy();
  });
});

describe("unavailable section", () => {
  const unavailable: RankingUnavailableEntry[] = [
    { institution_id: "D", institution_name: "Banque D", country_code: "CI", status: "needs_review", reason: "conflict" },
    { institution_id: "F", institution_name: "Banque F", country_code: "CI", status: "unavailable", reason: "missing" },
  ];

  it("lists institutions without a rank, with a translated reason", () => {
    renderWithIntl(<UnavailableList entries={unavailable} />);
    const rows = screen.getAllByTestId("unavailable-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Valeurs divergentes non vérifiées");
    expect(rows[1].textContent).toContain("Aucune valeur publiée");
    expect(screen.queryByTestId("rank-cell")).toBeNull(); // never ranked, never 0, never last
  });

  it("renders nothing when every institution is ranked", () => {
    const { container } = renderWithIntl(<UnavailableList entries={[]} />);
    expect(container.textContent).toBe("");
  });
});

describe("coverage", () => {
  it("expected 0 → —, never 0/1", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={null} representedCount={0} totalCount={0} />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(MISSING);
  });

  it("8 of 10 → 80 %", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={0.8} representedCount={8} totalCount={10} isPartial />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(`80,0${NBSP}%`);
  });
});

describe("rank history", () => {
  const history: RankHistory = {
    institution_id: "A",
    institution_name: "Banque A",
    metric_code: "total_actifs",
    period_type: "annual",
    data_scope: "individual",
    country_code: "CI",
    points: [
      { period_year: 2022, rank: null, value: null, ranking_status: "partial", status: "unavailable", reason: "missing", eligible_count: 3, ranked_count: 3, expected_count: 6, coverage_ratio: 0.5 },
      { period_year: 2023, rank: 4, value: 4e9, currency: "XOF", ranking_status: "partial", status: "extracted", eligible_count: 5, ranked_count: 5, expected_count: 6, coverage_ratio: 0.8333 },
    ],
  };

  it("shows the observed rank per year and — without an invented rank", () => {
    const { container } = renderWithIntl(<RankHistoryTable history={history} unit="XOF" />);
    const rows = screen.getAllByTestId("history-row");
    expect(rows[0].textContent).toContain(MISSING);
    expect(rows[1].textContent).toContain("4");
    expect(container.textContent).not.toMatch(/amélioration|dégradation|performance|improv|declin/i);
  });
});

describe("filters & URL parameters", () => {
  const params = (qs: string) => {
    const sp = new URLSearchParams(qs);
    return parseRankingParams((k) => sp.get(k) ?? "");
  };

  it("safe defaults and no invented year", () => {
    expect(params("")).toMatchObject({
      metric: DEFAULT_INDICATOR,
      year: null,
      country: UMOA,
      scope: "individual",
      period: "annual",
      order: "desc",
      page: 1,
    });
  });

  it("reads explicit filters and rejects invalid values", () => {
    expect(params("metric=ROA&year=2023&country=ci&scope=consolidated&period=semi_annual&order=asc&page=3")).toMatchObject({
      metric: "ROA",
      year: 2023,
      country: "CI",
      scope: "consolidated",
      period: "semi_annual",
      order: "asc",
      page: 3,
    });
    expect(params("metric=best_bank&year=20x4&scope=mixed")).toMatchObject({
      metric: DEFAULT_INDICATOR,
      year: null,
      scope: "individual",
    });
  });

  it("growth and ratios are annual only", () => {
    expect(supportsPeriodType("total_actifs", "semi_annual")).toBe(true);
    expect(supportsPeriodType("ROA", "semi_annual")).toBe(false);
    expect(supportsPeriodType("growth_pnb", "annual")).toBe(true);
  });

  it("locale switch keeps every ranking parameter", () => {
    const qs = new URLSearchParams("metric=ROE&year=2023&country=SN&scope=individual&period=annual&page=2");
    expect(buildLocaleHref("/rankings", qs)).toBe("/rankings?metric=ROE&year=2023&country=SN&scope=individual&period=annual&page=2");
  });

  it("comparison ids are distinct and capped at 5", () => {
    expect(parseIds("a, b,a,,c,d,e,f")).toEqual(["a", "b", "c", "d", "e"]);
  });
});

describe("pagination", () => {
  it("ranks come from the API; the page only slices", () => {
    renderWithIntl(<Pagination currentPage={2} pageSize={20} total={25} onPageChange={() => {}} />);
    expect(screen.getByText("Affichage de 21 à 25 sur 25 entrées")).toBeTruthy();
  });
});

describe("provenance of derived values", () => {
  beforeEach(() => {
    api.calls = [];
  });

  it("lists the source observations and loads the real record on click", async () => {
    renderWithIntl(
      <ProvenancePanel
        sources={[
          { data_id: "fd-num", metric_code: "resultat_net", period_year: 2024, period_type: "annual", scope: "individual", status: "verified", page_number: 12, source_name: "BCEAO" },
          { data_id: "fd-den", metric_code: "total_actifs", period_year: 2024, period_type: "annual", scope: "individual", status: "verified", page_number: null },
        ]}
        onClose={() => {}}
      />,
    );
    const sources = screen.getAllByTestId("provenance-source");
    expect(sources).toHaveLength(2);
    expect(sources[1].textContent).toContain(MISSING); // missing page → —
    fireEvent.click(sources[0]);
    await waitFor(() => expect(api.calls).toEqual(["fd-num"]));
  });
});

describe("comparisons", () => {
  const row = (id: string, value: number | null, extra: Partial<ComparisonRow> = {}): ComparisonRow => ({
    institution_id: id,
    institution_name: `Banque ${id}`,
    country_code: "CI",
    value,
    currency: "XOF",
    status: value === null ? "unavailable" : "verified",
    reason: value === null ? "missing" : null,
    data_id: value === null ? null : `fd-${id}`,
    provenance: [],
    ...extra,
  });
  const result = (rows: ComparisonRow[], status: InstitutionsComparison["status"] = "calculated"): InstitutionsComparison => ({
    metric_code: "total_actifs",
    kind: "metric",
    unit: "currency",
    period_year: 2024,
    period_type: "annual",
    data_scope: "individual",
    status,
    currency: "XOF",
    rows,
  });

  it("numerical difference with the first institution only", () => {
    const r = result([row("A", 5e9), row("B", 3e9), row("C", null)]);
    expect(differenceFromReference(r, r.rows[0])).toBeNull();
    expect(differenceFromReference(r, r.rows[1])).toBe(-2e9);
    expect(differenceFromReference(r, r.rows[2])).toBeNull(); // missing stays missing, never 0
  });

  it("no difference when the comparison is not homogeneous", () => {
    const r = result([row("A", 5e9), row("B", 3e9, { currency: "EUR" })]);
    expect(differenceFromReference(r, r.rows[1])).toBeNull();
    const blocked = result([row("A", null), row("B", null)], "needs_review");
    expect(differenceFromReference(blocked, blocked.rows[1])).toBeNull();
  });

  it("renders values, reasons and signed differences", () => {
    renderWithIntl(<ComparisonTable result={result([row("A", 5e9), row("B", 3e9), row("C", null)])} onProvenance={() => {}} />);
    const values = screen.getAllByTestId("comparison-value").map((c) => c.textContent);
    expect(values[2]).toContain(MISSING);
    expect(values[2]).toContain("Aucune valeur publiée");
    expect(screen.getAllByTestId("comparison-diff")[1].textContent).toBe(`-2,00${NBSP}Md${NBSP}FCFA`);
  });
});

describe("ratio labels (backend catalogue, no duplicated labels)", () => {
  function Label({ code }: { code: string }) {
    const label = useIndicatorLabel();
    return <span data-testid="indicator-label">{label(code)}</span>;
  }

  beforeEach(() => resetRatioDefinitionsCache());

  it("FR shows the ratio name, never the internal code", async () => {
    renderWithIntl(<Label code="DEPOTS_ACTIFS" />, "fr");
    await waitFor(() => expect(screen.getByTestId("indicator-label").textContent).toBe("Ratio dépôts sur actifs"));
    expect(screen.getByTestId("indicator-label").textContent).not.toContain("DEPOTS_ACTIFS");
  });

  it("EN shows the English ratio name", async () => {
    renderWithIntl(<Label code="DEPOTS_ACTIFS" />, "en");
    await waitFor(() => expect(screen.getByTestId("indicator-label").textContent).toBe("Deposits to Assets Ratio"));
  });

  it("metrics and growth keep their translated labels", async () => {
    renderWithIntl(<Label code="growth_pnb" />, "fr");
    expect(screen.getByTestId("indicator-label").textContent).toBe("Variation annuelle — Produit net bancaire");
  });
});

describe("coverage of a ranking blocked by heterogeneous currencies", () => {
  it("shows — and the reason, never 0/8 or 0 %", () => {
    const { container } = renderWithIntl(
      <CoverageIndicator coverageRatio={null} unavailableReason="Couverture indisponible — Devises incompatibles : aucune conversion n’est effectuée" />,
    );
    expect(screen.getByTestId("coverage-value").textContent).toBe(MISSING);
    expect(screen.getByTestId("coverage-unknown").textContent).toContain("Devises incompatibles");
    expect(container.textContent).not.toMatch(/0\/8|0,0\s%|0\s%/);
  });
});

describe("country / sector comparison not supported for ratios and growth", () => {
  const country: CountryComparison = {
    metric_code: "ROA", period_year: null, period_type: "annual", data_scope: "individual",
    status: "unavailable", reason: "aggregate_not_supported", country_code: "CI",
    country_total: null, country_coverage_ratio: null, umoa_total: null, umoa_coverage_ratio: null, share_percent: null,
  };
  const sector: SectorComparison = {
    metric_code: "growth_total_actifs", period_year: null, period_type: "annual", data_scope: "individual",
    status: "unavailable", reason: "aggregate_not_supported", institution: null, country_code: "CI",
    sector_total: null, sector_coverage_ratio: null, share_percent: null,
  };

  it("country ↔ UMOA: Indisponible + explanation, no numeric line", () => {
    renderWithIntl(<CountryComparisonCard result={country} countryName="Côte d'Ivoire" />);
    const card = screen.getByTestId("country-card");
    expect(card.textContent).toContain("Indisponible");
    expect(screen.getByTestId("not-supported-reason").textContent).toContain("Non disponible pour cet indicateur");
    expect(card.textContent).not.toMatch(/\b0\b|%/);
    expect(screen.queryByTestId("country-share")).toBeNull();
  });

  it("institution ↔ sector (EN): Unavailable + explanation", () => {
    renderWithIntl(<SectorComparisonCard result={sector} />, "en");
    expect(screen.getByTestId("sector-card").textContent).toContain("Unavailable");
    expect(screen.getByTestId("not-supported-reason").textContent).toContain("Not available for this indicator");
    expect(screen.queryByTestId("sector-share")).toBeNull();
  });
});

