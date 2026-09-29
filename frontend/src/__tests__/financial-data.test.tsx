/**
 * Phase 11 — UMOA financial data explorer.
 * Rows come from the (mocked) backend exactly as stored: the UI never fills,
 * totals, averages or converts a value.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { FinancialDataExplorerItem, FinancialDataFacets, Institution, PaginatedResponse } from "@/types";
import { MISSING } from "@/lib/formatters";
import { renderWithIntl } from "./helpers";

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  sets: [] as Record<string, unknown>[],
  explorerCalls: [] as Record<string, unknown>[],
  exportCalls: [] as Record<string, unknown>[],
  detailCalls: [] as string[],
  page: null as unknown,
  exportResult: { status: "ok", blob: new Blob(["a"]) } as unknown,
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
vi.mock("@/lib/api", () => ({
  getFinancialDataExplorer: (p: Record<string, unknown>) => {
    state.explorerCalls.push(p);
    return Promise.resolve(state.page);
  },
  getFinancialDataFacets: () => Promise.resolve(facets),
  getInstitutionsAll: () => Promise.resolve(institutions),
  exportFinancialDataCsv: (p: Record<string, unknown>) => {
    state.exportCalls.push(p);
    return Promise.resolve(state.exportResult);
  },
  getFinancialDataById: (id: string) => {
    state.detailCalls.push(id);
    return new Promise(() => {}); // stays loading: the call itself is asserted
  },
}));

import FinancialDataPage from "@/app/[locale]/financial-data/page";
import { parseExplorerParams } from "@/lib/financialData";

const facets: FinancialDataFacets = {
  period_years: [2024, 2023],
  period_types: ["annual", "semi_annual"],
  scopes: ["consolidated", "individual"],
  currencies: ["EUR", "XOF"],
  statuses: ["extracted", "needs_review", "rejected", "verified"],
  metric_codes: ["depots_clients", "total_actifs"],
};

const institutions: Institution[] = [
  { id: "A", name_official: "Banque A", institution_type: "bank", country_id: "ci", status: "active",
    country: { id: "ci", code: "CI", name_fr: "Côte d'Ivoire", name_en: "Côte d'Ivoire", is_active: true } },
  { id: "B", name_official: "Banque B", institution_type: "bank", country_id: "sn", status: "active",
    country: { id: "sn", code: "SN", name_fr: "Sénégal", name_en: "Senegal", is_active: true } },
];

const row = (over: Partial<FinancialDataExplorerItem> = {}): FinancialDataExplorerItem => ({
  id: "fd-1", institution_id: "A", institution_name: "Banque A", country_code: "CI", metric_code: "total_actifs",
  scope: "individual", period_type: "annual", period_year: 2024, period_label: null, value_original: "1000",
  unit_original: "millions", currency_original: "XOF", value_normalized: 1000000, unit_normalized: "unit",
  currency_normalized: "XOF", extraction_method: "pdf_table", status: "verified", source_id: "s",
  source_name: "BCEAO", document_id: "doc", document_title: "Rapport annuel", page_number: 84,
  qualification: "authoritative", authoritative_data_id: null, ...over,
});

const pageOf = (items: FinancialDataExplorerItem[], total = items.length): PaginatedResponse<FinancialDataExplorerItem> => ({
  items, total, page: 1, page_size: 25, has_next: total > 25, has_prev: false,
});

async function renderPage(locale: "fr" | "en" = "fr") {
  const view = renderWithIntl(<FinancialDataPage />, locale);
  await waitFor(() => expect(screen.queryByTestId("explorer-table") ?? screen.queryByRole("heading", { level: 3 })).toBeTruthy());
  return view;
}

beforeEach(() => {
  state.params = new URLSearchParams();
  state.sets = [];
  state.explorerCalls = [];
  state.exportCalls = [];
  state.detailCalls = [];
  state.page = pageOf([row()]);
  state.exportResult = { status: "ok", blob: new Blob(["a"]) };
});
afterEach(() => vi.restoreAllMocks());

describe("URL state", () => {
  it("defaults to annual + individual, never mixed", () => {
    const p = parseExplorerParams(() => "");
    expect(p.query.period_type).toBe("annual");
    expect(p.query.scope).toBe("individual");
    expect(p.page).toBe(1);
  });

  it("reads every filter, sort and page from the URL (deep link)", () => {
    const u = new URLSearchParams(
      "country=sn&inst=A,B,A&metric=total_actifs&year=2023&period=semi_annual&scope=consolidated&currency=EUR&status=verified&sort=value&order=desc&page=3",
    );
    const p = parseExplorerParams((k) => u.get(k) ?? "");
    expect(p.query).toEqual({
      institution_ids: ["A", "B"], country_code: "SN", metric_code: "total_actifs", period_year: 2023,
      period_type: "semi_annual", scope: "consolidated", currency_normalized: "EUR", status: "verified",
      sort: "value", order: "desc",
    });
    expect(p.page).toBe(3);
  });

  it("ignores invalid country, sort and page values", () => {
    const u = new URLSearchParams("country=FR&sort=score&page=-2&year=abc");
    const p = parseExplorerParams((k) => u.get(k) ?? "");
    expect(p.query.country_code).toBeUndefined();
    expect(p.query.sort).toBeUndefined();
    expect(p.query.period_year).toBeUndefined();
    expect(p.page).toBe(1);
  });

  it("sends the URL filters and the page to the backend", async () => {
    state.params = new URLSearchParams("country=CI&year=2024&page=2");
    await renderPage();
    expect(state.explorerCalls.at(-1)).toMatchObject({
      country_code: "CI", period_year: 2024, period_type: "annual", scope: "individual", page: 2, page_size: 25,
    });
  });
});

describe("filters", () => {
  it("a filter change writes the URL and resets pagination", async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText("Pays"), { target: { value: "SN" } });
    expect(state.sets.at(-1)).toEqual({ country: "SN", page: null });
    fireEvent.change(screen.getByLabelText("Devise"), { target: { value: "EUR" } });
    expect(state.sets.at(-1)).toEqual({ currency: "EUR", page: null });
  });

  it("indicator, currency and status options come from stored values with FR labels", async () => {
    await renderPage();
    const indicator = screen.getByLabelText("Indicateur") as HTMLSelectElement;
    expect([...indicator.options].map((o) => o.value)).toEqual(["", "depots_clients", "total_actifs"]);
    const currency = screen.getByLabelText("Devise") as HTMLSelectElement;
    expect([...currency.options].map((o) => o.text)).toEqual(["Tous", "EUR", "FCFA"]);
    const status = screen.getByLabelText("Statut") as HTMLSelectElement;
    expect(status.options[0].text).toBe("Tous (hors rejetés)");
  });

  it("institution search adds to a multi-selection stored in the URL", async () => {
    state.params = new URLSearchParams("inst=B");
    await renderPage();
    await waitFor(() => expect(within(screen.getByTestId("selected-institutions")).getByText("Banque B")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Institution"), { target: { value: "banque a" } });
    fireEvent.click(await screen.findByRole("option", { name: /Banque A/ }));
    expect(state.sets.at(-1)).toEqual({ inst: "B,A", page: null });
    fireEvent.click(screen.getByRole("button", { name: "Retirer Banque B" }));
    expect(state.sets.at(-1)).toEqual({ inst: null, page: null });
  });
});

describe("table", () => {
  it("shows every column with the value as stored and a link to the institution", async () => {
    await renderPage();
    const r = screen.getAllByTestId("explorer-row")[0];
    expect(within(r).getByRole("link", { name: "Banque A" }).getAttribute("href")).toBe("/institutions/A");
    expect(r.textContent).toContain("Côte d'Ivoire");
    expect(r.textContent).toContain("Total actifs");
    expect(r.textContent).toContain("Comptes individuels");
    expect(r.textContent).toContain("Annuel");
    expect(r.textContent).toContain("FCFA");
    expect(r.textContent).toContain("Valeur retenue");
    expect(r.textContent).toContain("BCEAO");
    expect(r.textContent).toContain("p. 84");
  });

  it("a missing value is shown as —, never 0", async () => {
    state.page = pageOf([row({ value_normalized: null, qualification: "missing_value", currency_normalized: null })]);
    await renderPage();
    expect(screen.getByTestId("explorer-value").textContent).toBe(MISSING);
    expect(screen.getByTestId("explorer-row").textContent).not.toMatch(/\b0\b/);
  });

  it("rows of different currencies are listed, never totalled or converted", async () => {
    state.page = pageOf([row(), row({ id: "fd-2", currency_normalized: "EUR", value_normalized: 2 })]);
    await renderPage();
    const values = screen.getAllByTestId("explorer-value").map((c) => c.textContent);
    expect(values).toHaveLength(2);
    expect(document.body.textContent).not.toMatch(/total\s*:/i);
    expect(screen.getAllByTestId("explorer-row")[1].textContent).toContain("EUR");
  });

  it("sorting is delegated to the backend through the URL and toggles the order", async () => {
    state.params = new URLSearchParams("sort=value&order=asc");
    await renderPage();
    expect(screen.getByTestId("value-sort-note")).toBeTruthy();
    fireEvent.click(screen.getByTestId("sort-value"));
    expect(state.sets.at(-1)).toEqual({ sort: "value", order: "desc", page: null });
    fireEvent.click(screen.getByTestId("sort-institution"));
    expect(state.sets.at(-1)).toEqual({ sort: "institution", order: "asc", page: null });
  });
});

describe("pagination and empty state", () => {
  it("paginates with the backend total", async () => {
    state.page = pageOf([row()], 60);
    await renderPage();
    expect(screen.getByTestId("explorer-count").textContent).toBe("60 observations");
    fireEvent.click(screen.getByRole("button", { name: /suivant/i }));
    expect(state.sets.at(-1)).toEqual({ page: 2 });
  });

  it.each([
    ["fr", "Aucune donnée disponible"],
    ["en", "No data available"],
  ] as const)("empty selection (%s)", async (locale, text) => {
    state.page = pageOf([]);
    renderWithIntl(<FinancialDataPage />, locale);
    expect(await screen.findByText(text)).toBeTruthy();
    expect(screen.queryByTestId("explorer-table")).toBeNull();
  });
});

describe("provenance", () => {
  it("the source opens the existing provenance panel on the real record", async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId("explorer-source"));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(state.detailCalls).toEqual(["fd-1"]);
  });
});

describe("export", () => {
  it("exports with the same filters", async () => {
    state.params = new URLSearchParams("country=SN&metric=total_actifs");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    await renderPage();
    await act(async () => {
      fireEvent.click(screen.getByTestId("export-csv"));
    });
    expect(state.exportCalls).toEqual([parseExplorerParams((k) => state.params.get(k) ?? "").query]);
    expect(click).toHaveBeenCalled();
  });

  it("refused by the backend → 'refine your filters' (EN)", async () => {
    state.exportResult = { status: "too_large" };
    await renderPage("en");
    await act(async () => {
      fireEvent.click(screen.getByTestId("export-csv"));
    });
    expect(screen.getByTestId("export-too-large").textContent).toContain("Export unavailable — refine your filters");
  });

  it("disabled above the bound without calling the backend (FR)", async () => {
    state.page = pageOf([row()], 5001);
    await renderPage();
    expect((screen.getByTestId("export-csv") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("export-too-large").textContent).toContain("Export indisponible — affinez vos filtres");
    expect(state.exportCalls).toEqual([]);
  });
});

describe("FR / EN", () => {
  it("English UI has no French label", async () => {
    state.page = pageOf([row({ qualification: "superseded", status: "extracted" })]);
    await renderPage("en");
    const text = document.body.textContent ?? "";
    expect(text).toContain("UMOA financial data");
    expect(text).toContain("Another observation retained");
    expect(text).toContain("Individual accounts");
    expect(text).toContain("Total assets");
    for (const fr of ["Valeur", "Périmètre", "Devise", "Aucune", "Comptes individuels", "Total actifs"]) expect(text).not.toContain(fr);
  });
});
