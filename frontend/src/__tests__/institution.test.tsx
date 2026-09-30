/**
 * Phase 10 — Financial Intelligence Explorer (institution search & detail).
 * Every figure comes from the (mocked) backend profile endpoints; the UI never
 * computes, fills or converts a value.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import type {
  HistorySeries,
  Institution,
  InstitutionFinancials,
  InstitutionHistory,
  InstitutionProfileCoverage,
  ProvenanceRef,
} from "@/types";
import { MISSING } from "@/lib/formatters";
import { renderWithIntl } from "./helpers";

const prov = (id: string, page: number | null = 84): ProvenanceRef => ({
  data_id: id,
  metric_code: "total_actifs",
  period_year: 2024,
  period_type: "annual",
  scope: "individual",
  document_id: "doc-1",
  document_title: "Rapport annuel 2024",
  source_name: "BCEAO",
  page_number: page,
  status: "verified",
});

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  sets: [] as Record<string, unknown>[],
  apiCalls: [] as string[],
  institutions: [] as unknown[],
  profile: {} as Record<string, unknown>,
}));

vi.mock("@/lib/useQueryParams", () => ({
  useQueryParams: () => ({
    get: (k: string) => state.params.get(k) ?? "",
    set: (u: Record<string, unknown>) => state.sets.push(u),
    searchParams: state.params,
  }),
}));
vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api", () => {
  const call = (name: string, value: unknown) => {
    state.apiCalls.push(name);
    return Promise.resolve(value);
  };
  return {
    getInstitutions: (p: { search?: string }) => {
      state.apiCalls.push(`getInstitutions:${p.search ?? ""}`);
      return Promise.resolve({ items: state.institutions, total: state.institutions.length, page: 1, page_size: 15, has_next: false, has_prev: false });
    },
    getInstitutionById: () => call("getInstitutionById", state.profile.institution),
    getDocuments: () => call("getDocuments", { items: [], total: 0, page: 1, page_size: 100, has_next: false, has_prev: false }),
    getInstitutionFinancials: (_id: string, p: Record<string, unknown>) => {
      state.apiCalls.push(`financials:${p.data_scope}:${p.period_type}`);
      return Promise.resolve(state.profile.financials);
    },
    getInstitutionHistory: () => call("history", state.profile.history),
    getInstitutionRatios: () => call("ratios", state.profile.ratios),
    getInstitutionGrowth: () => call("growth", state.profile.growth),
    getInstitutionCoverage: () => call("coverage", state.profile.coverage),
    getFinancialDataById: (id: string) => {
      state.apiCalls.push(`detail:${id}`);
      return new Promise(() => {}); // stays loading: the call itself is asserted
    },
    getRatioDefinitions: () =>
      Promise.resolve([{ ratio_code: "DEPOTS_ACTIFS", name_fr: "Ratio dépôts sur actifs", name_en: "Deposits to Assets Ratio" }]),
  };
});

import InstitutionsListPage from "@/app/[locale]/institutions/page";
import InstitutionDetailPage from "@/app/[locale]/institutions/[id]/page";
import { HistoryCharts, isChartable } from "@/components/institutions/HistoryCharts";
import { CoveragePanel } from "@/components/institutions/CoveragePanel";
import { KeyFinancials } from "@/components/institutions/KeyFinancials";
import { GrowthTable } from "@/components/institutions/GrowthTable";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { resetRatioDefinitionsCache } from "@/lib/useRatioDefinitions";

const institution: Institution = {
  id: "A",
  name_official: "Banque A",
  institution_type: "bank",
  country_id: "c-ci",
  country: { id: "c-ci", code: "CI", name_fr: "Côte d'Ivoire", name_en: "Côte d'Ivoire", is_active: true },
  status: "active",
};

const selection = { scopes: ["individual"], period_types: ["annual"], years: [2024, 2022, 2021] };

const financials: InstitutionFinancials = {
  institution_id: "A",
  period_year: 2024,
  period_type: "annual",
  data_scope: "individual",
  status: "partial",
  selection,
  values: [
    {
      metric_code: "total_actifs", period_year: 2024, period_type: "annual", data_scope: "individual",
      value_original: "1000 (millions)", unit_original: "millions", currency_original: "XOF",
      value_normalized: 1e9, unit_normalized: "unit", currency: "XOF", status: "verified", data_id: "fd-ta", provenance: prov("fd-ta"),
    },
  ],
  unavailable: [
    { metric_code: "depots_clients", period_year: 2024, status: "unavailable", reason: "missing" },
    { metric_code: "capitaux_propres", period_year: 2024, status: "needs_review", reason: "conflict" },
  ],
};

const series = (over: Partial<HistorySeries> = {}): HistorySeries => ({
  metric_code: "total_actifs",
  status: "partial",
  currency: "XOF",
  points: [2021, 2022, 2024].map((y, i) => ({
    period_year: y, value: (8 + i) * 1e8, currency: "XOF", unit_normalized: "unit", status: "extracted",
    data_id: `fd-${y}`, provenance: prov(`fd-${y}`),
  })),
  missing_years: [2023],
  excluded_years: [],
  ...over,
});

const history: InstitutionHistory = {
  institution_id: "A", period_type: "annual", data_scope: "individual", status: "partial", selection, series: [series()],
};

const coverage = (over: Partial<InstitutionProfileCoverage> = {}): InstitutionProfileCoverage => ({
  institution_id: "A", period_type: "annual", data_scope: "individual", status: "partial",
  first_year: 2021, last_year: 2024, available_years: [2021, 2022, 2024], missing_years: [2023],
  available_years_count: 3, expected_years_count: 4, coverage_ratio: 0.75,
  quality: { total_observations: 11, verified: 1, reviewed: 0, extracted: 8, needs_review: 1, rejected: 1, conflicts: 1, missing_years: 1 },
  documents: [{ document_id: "doc-1", title: "Rapport annuel 2024", source_name: "BCEAO", period_years: [2024], pages: [84], values_count: 2 }],
  ...over,
});

beforeEach(() => {
  state.params = new URLSearchParams();
  state.sets = [];
  state.apiCalls = [];
  state.institutions = [institution];
  state.profile = {
    institution,
    financials,
    history,
    ratios: { institution_id: "A", period_year: 2024, period_type: "annual", data_scope: "individual", status: "partial", items: [] },
    growth: {
      institution_id: "A", period_year: 2024, period_type: "annual", data_scope: "individual", status: "unavailable", reason: "no_computable_value",
      items: [{
        metric_code: "total_actifs", institution_id: "A", current_year: 2024, previous_year: 2023, current_value: 1e9, previous_value: null,
        absolute_change: null, growth_rate: null, growth_percent: null, currency: "XOF", status: "unavailable",
        reason: "Missing component: total_actifs (2023)", components: [], calculated_at: "2026-01-01",
      }],
    },
    coverage: coverage(),
  };
  resetRatioDefinitionsCache();
});

/** Already-resolved thenable: React 19 `use()` reads it synchronously (no Suspense round-trip in jsdom). */
function resolved<T>(value: T): Promise<T> {
  const p = Promise.resolve(value) as Promise<T> & { status?: string; value?: T };
  p.status = "fulfilled";
  p.value = value;
  return p;
}

const detail = (locale: "fr" | "en" = "fr") =>
  renderWithIntl(<InstitutionDetailPage params={resolved({ id: "A", locale })} />, locale);

describe("institution search", () => {
  afterEach(() => vi.useRealTimers());

  it("lists institutions and pushes the debounced query to the URL", async () => {
    renderWithIntl(<InstitutionsListPage />);
    await waitFor(() => expect(screen.getByText("Banque A")).toBeTruthy());
    expect(screen.getByText("Banque A").closest("a")?.getAttribute("href")).toBe("/institutions/A");

    vi.useFakeTimers();
    fireEvent.change(screen.getByPlaceholderText("Nom d’établissement ou mot-clé...".replace("’", "'")), {
      target: { value: "Banque" },
    });
    expect(state.sets).toEqual([]); // nothing sent while typing
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(state.sets).toContainEqual({ q: "Banque", page: null });
  });
});

describe("institution detail", () => {
  it("renders the explorer sections from the backend profile", async () => {
    detail();
    await waitFor(() => expect(screen.getByTestId("key-financials")).toBeTruthy());
    for (const id of ["institution-header", "financials-section", "history-section", "ratios-section", "growth-section", "coverage-section", "sources-section"]) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
    expect(screen.getByText("Banque A")).toBeTruthy();
    expect(state.apiCalls).toContain("financials:individual:annual"); // safe defaults
    // Phase 13: Institution -> Financial Data Explorer and Institution -> Deals, filtered on this institution.
    expect(screen.getByTestId("institution-financial-data-link").getAttribute("href")).toMatch(/^\/financial-data\?inst=/);
    expect(screen.getByTestId("institution-deals-link").getAttribute("href")).toMatch(/^\/deals\?bank=/);
  });

  it("missing and non-certified values show — and their reason, never 0", async () => {
    detail();
    await waitFor(() => expect(screen.getByTestId("key-depots_clients")).toBeTruthy());
    const deposits = screen.getByTestId("key-depots_clients").textContent ?? "";
    expect(deposits).toContain(MISSING);
    expect(deposits).toContain("Aucune valeur publiée");
    expect(deposits).not.toMatch(/\b0\b/);
    expect(screen.getByTestId("key-capitaux_propres").textContent).toContain("Valeurs divergentes non vérifiées");
  });

  it("unavailable selection: explicit state, no figure", async () => {
    state.profile.financials = { ...financials, status: "unavailable", reason: "no_data_for_selection", period_year: null, values: [], unavailable: [] };
    state.profile.history = { ...history, status: "unavailable", reason: "no_data_for_selection", series: [] };
    state.profile.coverage = coverage({ status: "unavailable", reason: "no_data_for_selection", coverage_ratio: null, expected_years_count: null, first_year: null, last_year: null, available_years: [], missing_years: [], available_years_count: 0, documents: [] });
    detail();
    await waitFor(() => expect(screen.getByTestId("profile-unavailable")).toBeTruthy());
    expect(screen.getByTestId("profile-unavailable").textContent).toContain("Aucune donnée pour ce périmètre");
    expect(screen.getByTestId("history-unavailable")).toBeTruthy();
    expect(screen.getByTestId("coverage-years").textContent).toBe(MISSING);
  });

  it("scope and period selectors write the URL and flag unpublished options", async () => {
    detail();
    await waitFor(() => expect(screen.getByTestId("scope-select")).toBeTruthy());
    const scope = screen.getByTestId("scope-select") as HTMLSelectElement;
    expect([...scope.options].map((o) => o.textContent)).toEqual(["Comptes individuels", "Comptes consolidés — non publié"]);
    fireEvent.change(scope, { target: { value: "consolidated" } });
    expect(state.sets).toContainEqual({ scope: "consolidated", year: null });
    fireEvent.change(screen.getByTestId("period-select"), { target: { value: "semi_annual" } });
    expect(state.sets).toContainEqual({ period: "semi_annual", year: null });
  });

  it("selected scope / period from the URL are sent to the backend (never mixed)", async () => {
    state.params = new URLSearchParams("scope=consolidated&period=semi_annual");
    detail();
    await waitFor(() => expect(state.apiCalls).toContain("financials:consolidated:semi_annual"));
  });

  it("provenance opens the real record by data_id", async () => {
    detail();
    await waitFor(() => expect(screen.getByTestId("key-provenance")).toBeTruthy());
    fireEvent.click(screen.getByTestId("key-provenance"));
    await waitFor(() => expect(state.apiCalls).toContain("detail:fd-ta"));
  });

  it("English locale: no French label in the explorer", async () => {
    detail("en");
    await waitFor(() => expect(screen.getByTestId("key-financials")).toBeTruthy());
    const text = screen.getByTestId("key-financials").textContent ?? "";
    expect(text).toContain("Key figures");
    expect(text).not.toMatch(/Chiffres clés|Aucune valeur|Valeurs divergentes/);
  });
});

describe("historical chart", () => {
  it("draws only real points, marks the gap, shows unit and currency", () => {
    const { container } = renderWithIntl(<HistoryCharts history={history} onProvenance={() => {}} />);
    expect(container.querySelectorAll('[data-testid="line-segment"]')).toHaveLength(2); // 2021–2022, 2024
    expect(screen.getAllByTestId("history-point").map((r) => r.textContent?.slice(0, 4))).toEqual(["2021", "2022", "2024"]);
    expect(screen.getByTestId("missing-years").textContent).toContain("2023");
    expect(screen.getByTestId("series-unit").textContent).toContain("FCFA");
  });

  it("one point or heterogeneous currencies: no chart, explicit message", () => {
    const single = series({ points: series().points.slice(0, 1), missing_years: [] });
    const mixed = series({ status: "needs_review", reason: "heterogeneous_currency", currency: null });
    expect(isChartable(single)).toBe(false);
    expect(isChartable(mixed)).toBe(false);
    renderWithIntl(<HistoryCharts history={{ ...history, series: [single, mixed] }} onProvenance={() => {}} />);
    const msgs = screen.getAllByTestId("insufficient-data").map((m) => m.textContent);
    expect(msgs[0]).toContain("Données insuffisantes");
    expect(msgs[1]).toContain("Devises incompatibles");
  });

  it("English: Insufficient data", () => {
    const single = series({ points: series().points.slice(0, 1), missing_years: [] });
    renderWithIntl(<HistoryCharts history={{ ...history, series: [single] }} onProvenance={() => {}} />, "en");
    expect(screen.getByTestId("insufficient-data").textContent).toContain("Insufficient data");
  });
});

describe("coverage, growth, key figures, ratios", () => {
  it("coverage with a defined denominator, and — without data", () => {
    const { unmount } = renderWithIntl(<CoveragePanel coverage={coverage()} />);
    expect(screen.getByTestId("coverage-years").textContent).toBe("2021–2024 : 3/4 exercices disponibles");
    expect(screen.getByTestId("quality-q_rejected").textContent).toBe("1");
    expect(screen.getByTestId("coverage-panel").textContent).not.toMatch(/score|\/5|Excellent|Bon\b/i);
    unmount();
    renderWithIntl(<CoveragePanel coverage={coverage({ status: "unavailable", reason: "no_data", coverage_ratio: null, expected_years_count: null })} />);
    expect(screen.getByTestId("coverage-years").textContent).toBe(MISSING);
    expect(screen.getByTestId("coverage-ratio").textContent).toContain("Couverture indisponible");
    expect(screen.getByTestId("coverage-ratio").textContent).not.toMatch(/0\s?%/);
  });

  it("growth with a missing period: —, translated reason, never 0 %", () => {
    renderWithIntl(<GrowthTable items={(state.profile.growth as { items: never[] }).items} />);
    const cell = screen.getByTestId("growth-pct");
    expect(cell.textContent).toContain(MISSING);
    expect(cell.textContent).toContain("Période requise indisponible");
    expect(cell.textContent).not.toMatch(/0,00|Missing component/);
  });

  it("key figures: value with currency and provenance button", () => {
    renderWithIntl(<KeyFinancials financials={financials} onProvenance={() => {}} />);
    expect(screen.getByTestId("key-total_actifs").textContent).toContain("1,00 Md FCFA");
  });

  it("ratio labels come from the backend catalogue in FR and EN", async () => {
    const ratio = {
      ratio_code: "DEPOTS_ACTIFS", ratio_name: "Ratio dépôts sur actifs", institution_id: "A", period_year: 2024, period_type: "annual",
      value: 0.6, value_percent: 60, unit: "%", status: "calculated", formula_used: "depots_clients / total_actifs", components: [], calculated_at: "x",
    };
    const { unmount } = renderWithIntl(<RatioDataTable ratios={[ratio]} />, "fr");
    await waitFor(() => expect(screen.getByText("Ratio dépôts sur actifs")).toBeTruthy());
    unmount();
    resetRatioDefinitionsCache();
    renderWithIntl(<RatioDataTable ratios={[ratio]} />, "en");
    await waitFor(() => expect(screen.getByText("Deposits to Assets Ratio")).toBeTruthy());
    expect(screen.queryByText("Ratio dépôts sur actifs")).toBeNull();
  });
});
