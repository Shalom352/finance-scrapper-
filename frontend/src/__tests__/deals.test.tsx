/**
 * Phase 13 — Deal Intelligence (explorer, detail, review center tab, deal review).
 * Every value comes from the (mocked) backend: NULL is shown as unavailable (never 0),
 * amounts stay per currency, a duplicate is only a candidate until a human decides.
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { DealAnalytics, DealDetail, DealDuplicate, DealListItem, PaginatedResponse, ReviewEvent } from "@/types";
import { renderWithIntl } from "./helpers";

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  sets: [] as Record<string, unknown>[],
  dealCalls: [] as Record<string, unknown>[],
  analyticsCalls: [] as string[],
  posts: [] as { id: string; action: string; body: Record<string, unknown> }[],
  decisions: [] as { id: string; body: Record<string, unknown> }[],
  deals: null as unknown,
  deal: null as unknown,
  history: [] as unknown[],
  analytics: null as unknown,
  queue: null as unknown,
  dups: null as unknown,
  dealError: null as number | null,
  postError: null as number | null,
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
  class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  }
  return {
    ApiError,
    getDeals: (p: Record<string, unknown>) => {
      state.dealCalls.push(p);
      return Promise.resolve(state.deals);
    },
    getInstitutionsAll: () =>
      Promise.resolve([{ id: "inst-a", name_official: "Banque A", institution_type: "bank", country_id: "ci", status: "active" }]),
    getDealAnalytics: (d: string) => {
      state.analyticsCalls.push(d);
      return Promise.resolve(state.analytics);
    },
    getDeal: () => (state.dealError ? Promise.reject(new ApiError(state.dealError, "x")) : Promise.resolve(state.deal)),
    getDealHistory: () => Promise.resolve(state.history),
    getDealQueue: () => Promise.resolve(state.queue),
    getOpenDealDuplicates: () => Promise.resolve(state.dups),
    postDealReviewAction: (id: string, action: string, body: Record<string, unknown>) => {
      state.posts.push({ id, action, body });
      return state.postError ? Promise.reject(new ApiError(state.postError, "x")) : Promise.resolve({});
    },
    postReviewAction: () => Promise.resolve({}),
    postDuplicateDecision: (id: string, body: Record<string, unknown>) => {
      state.decisions.push({ id, body });
      return Promise.resolve({});
    },
  };
});

import DealsPage from "@/app/[locale]/deals/page";
import DealPage from "@/app/[locale]/deals/[dealId]/page";
import DealReviewPage from "@/app/[locale]/data-quality/deals/[dealId]/page";
import { DealQueue } from "@/components/data-quality/DealQueue";

const page = <T,>(items: T[]): PaginatedResponse<T> => ({
  items, total: items.length, page: 1, page_size: 20, has_next: false, has_prev: false,
});

const listItem = (over: Partial<DealListItem> = {}): DealListItem => ({
  id: "deal-1", title: "Prêt syndiqué Autoroute du Nord", deal_type: "syndicated_loan", status: "needs_review",
  country_code: "SN", sector: "infrastructure", project_name: "Autoroute du Nord", amount: 25000000000, currency: "XOF",
  unit: "units", announcement_date: null, signing_date: "2024-03-15", borrowers: ["État du Sénégal"],
  arrangers: ["Banque A"], duplicate_candidates: 0, merged_into_deal_id: null, updated_at: "2026-09-01T10:00:00.123456Z",
  ...over,
});

const candidate = (over: Partial<DealDuplicate> = {}): DealDuplicate => ({
  id: "cand-1", other_deal_id: "deal-2", other_deal_title: "Financement autoroute (Sénégal)", other_deal_status: "needs_review",
  matched_criteria: ["borrower", "project", "currency_amount", "dates"], state: "duplicate_candidate", primary_deal_id: null,
  decided_by: null, decided_at: null, decision_reason: null, ...over,
});

const detail = (over: Partial<DealDetail> = {}): DealDetail => ({
  ...listItem(),
  amount_original: "25 milliards FCFA", interest_rate: null, interest_rate_type: null, benchmark: null, spread_bps: null,
  maturity_months: null, grace_period_months: null, fees: null, guarantees: null, financial_close_date: null,
  closing_date: null, notes: null, verified_at: null, verified_by: null, created_at: "2026-09-01T10:00:00Z",
  participants: [
    { id: "p1", participant_name: "État du Sénégal", institution_id: null, institution_name: null, role: "borrower",
      commitment_amount: null, commitment_currency: null, deal_source_id: "src-1" },
    { id: "p2", participant_name: "Banque A", institution_id: "inst-a", institution_name: "Banque A", role: "arranger",
      commitment_amount: null, commitment_currency: null, deal_source_id: "src-1" },
  ],
  sources: [
    { id: "src-1", deal_id: "deal-1", document_id: "doc-1", document_title: "Communiqué A", document_url: null,
      source_id: "s1", source_name: "BCEAO", page_number: 3, excerpt: "Tableau des financements", fields: ["title", "amount", "currency"] },
    { id: "src-2", deal_id: "deal-1", document_id: "doc-2", document_title: "Note C", document_url: null,
      source_id: "s2", source_name: "Commission Bancaire", page_number: 7, excerpt: null, fields: ["signing_date"] },
  ],
  field_provenance: { title: ["src-1"], amount: ["src-1"], currency: ["src-1"], signing_date: ["src-2"] },
  duplicates: [], merged_deals: [], allowed_actions: ["review", "reject"],
  ...over,
});

const events: ReviewEvent[] = [
  { id: "e1", financial_data_id: null, deal_id: "deal-1", action: "import", previous_status: "none", new_status: "needs_review",
    reason: "Structured import: deals.json", actor: "analyst-1", value_before: null, value_after: 25000000000,
    created_at: "2026-09-01T10:00:00Z" },
];

const analytics: DealAnalytics = {
  dimension: "country", amount_basis: "reviewed_or_verified_per_currency_and_unit",
  rows: [{ key: "SN", label: "SN", deals: 2, by_status: { verified: 2 }, deals_without_amount: 0,
    amounts: [{ currency: "EUR", unit: "units", total: 10000000, deals: 1 }, { currency: "XOF", unit: "units", total: 25000000000, deals: 1 }] }],
};

const params = (dealId: string) =>
  Object.assign(Promise.resolve({ dealId, locale: "fr" }), { status: "fulfilled", value: { dealId, locale: "fr" } });

beforeEach(() => {
  state.params = new URLSearchParams();
  state.sets = [];
  state.dealCalls = [];
  state.analyticsCalls = [];
  state.posts = [];
  state.decisions = [];
  state.deals = page([listItem()]);
  state.deal = detail();
  state.history = events;
  state.analytics = analytics;
  state.queue = page([listItem()]);
  state.dups = page([candidate()]);
  state.dealError = null;
  state.postError = null;
});

const NO_JUNK = /\b(undefined|NaN|null)\b|\[object Object\]/;

describe("Deal explorer", () => {
  it("lists deals from the backend with the URL filters and never shows junk values", async () => {
    state.params = new URLSearchParams("country=SN&participant_role=arranger&bank=inst-a&year=2024&currency=XOF&deal_type=bogus");
    const view = renderWithIntl(<DealsPage />, "fr");
    await screen.findByTestId("deal-table");
    expect(state.dealCalls[0]).toMatchObject({ country: "SN", participant_role: "arranger", bank: "inst-a", year: 2024, currency: "XOF", page: 1 });
    expect(state.dealCalls[0].deal_type).toBeUndefined(); // an unknown code in the URL is ignored, never guessed
    const row = screen.getByTestId("deal-row");
    expect(row.textContent).toContain("Prêt syndiqué");
    expect(row.textContent).toContain("État du Sénégal");
    expect(row.textContent).toMatch(/FCFA/);
    expect(view.container.textContent).not.toMatch(NO_JUNK);
  });

  it("changing a filter writes the URL and resets the page", async () => {
    renderWithIntl(<DealsPage />, "en");
    await screen.findByTestId("deal-table");
    fireEvent.change(screen.getByTestId("deal-filter-status"), { target: { value: "verified" } });
    expect(state.sets.at(-1)).toEqual({ status: "verified", page: null });
  });

  it("shows an explicit empty state", async () => {
    state.deals = page([]);
    renderWithIntl(<DealsPage />, "en");
    expect(await screen.findByText("No deal")).toBeTruthy();
  });

  it("descriptive panel keeps each currency separate and never ranks", async () => {
    renderWithIntl(<DealsPage />, "en");
    const amounts = await screen.findByTestId("deal-analytics-amounts");
    const lines = within(amounts).getAllByRole("listitem").map((li) => li.textContent);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatch(/EUR/);
    expect(lines[1]).toMatch(/FCFA/);
    expect(screen.getByTestId("deal-analytics").textContent).not.toMatch(/25,010,000,000/); // never summed across currencies
    fireEvent.change(screen.getByTestId("deal-analytics-dimension"), { target: { value: "institution" } });
    expect(state.sets.at(-1)).toEqual({ dim: "institution" });
  });
});

describe("Deal detail", () => {
  it("renders every section; unpublished terms are 'unavailable', never 0", async () => {
    const view = renderWithIntl(<DealPage params={params("deal-1")} />, "en");
    await screen.findByTestId("deal-title");
    for (const id of ["deal-summary", "deal-terms", "deal-participants", "deal-timeline", "deal-project",
      "deal-guarantees", "deal-sources", "deal-duplicates", "deal-history"]) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
    for (const f of ["interest_rate", "spread_bps", "maturity_months", "grace_period_months", "fees", "guarantees"]) {
      expect(screen.getByTestId(`deal-field-${f}`).textContent).toMatch(/Unavailable/);
    }
    expect(screen.getByTestId("deal-field-closing_date").textContent).toMatch(/Not published/);
    expect(screen.getByTestId("deal-field-signing_date").textContent).toContain("03/15/2024"); // no time-zone shift
    expect(screen.getByTestId("deal-field-amount").textContent).toMatch(/p\. 3/); // field-level provenance
    expect(view.container.textContent).not.toMatch(NO_JUNK);
  });

  it("links participants to the institution directory only when the id is known (Deal → Institution)", async () => {
    renderWithIntl(<DealPage params={params("deal-1")} />, "fr");
    await screen.findByTestId("deal-title");
    const [borrower, arranger] = screen.getAllByTestId("deal-participant");
    const hrefs = (el: HTMLElement) => within(el).queryAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs(borrower).filter((h) => h?.startsWith("/institutions"))).toEqual([]);
    expect(borrower.textContent).toMatch(/Hors répertoire/);
    expect(hrefs(arranger)).toContain("/institutions/inst-a");
  });

  it("a duplicate is a candidate until a human decides — never 'confirmed'", async () => {
    state.deal = detail({ duplicates: [candidate()], duplicate_candidates: 1 });
    renderWithIntl(<DealPage params={params("deal-1")} />, "en");
    const dup = await screen.findByTestId("deal-duplicate");
    expect(dup.textContent).toMatch(/Duplicate candidate — needs review/);
    expect(dup.textContent).toMatch(/Same borrower/);
    expect(document.body.textContent).not.toMatch(/confirmed/i);
  });

  it("a decided candidate names the human who decided", async () => {
    state.deal = detail({ duplicates: [candidate({ state: "same_deal", decided_by: "analyst-3" })] });
    renderWithIntl(<DealPage params={params("deal-1")} />, "fr");
    expect((await screen.findByTestId("deal-duplicate")).textContent).toMatch(/Même transaction \(décidé par analyst-3\)/);
  });

  it("an attached deal says so and keeps its sources visible on the primary deal", async () => {
    state.deal = detail({
      merged_deals: [{ id: "deal-2", title: "Doublon", status: "needs_review", participants: [],
        sources: [{ id: "src-9", deal_id: "deal-2", document_id: "doc-9", document_title: "Rapport B", document_url: null,
          source_id: "s1", source_name: "BCEAO", page_number: 12, excerpt: null, fields: ["title"] }] }],
    });
    renderWithIntl(<DealPage params={params("deal-1")} />, "en");
    const merged = await screen.findByTestId("deal-merged");
    expect(merged.textContent).toContain("Rapport B");
  });

  it("404 is 'not found', any other failure is an error state", async () => {
    state.dealError = 404;
    renderWithIntl(<DealPage params={params("nope")} />, "en");
    expect(await screen.findByText("Deal not found.")).toBeTruthy();
  });

  it("history shows the import as a creation, with its actor", async () => {
    renderWithIntl(<DealPage params={params("deal-1")} />, "en");
    const item = await screen.findByTestId("dq-history-item");
    expect(item.textContent).toMatch(/Structured import/);
    expect(item.textContent).toMatch(/created/);
    expect(item.textContent).toMatch(/analyst-1/);
  });
});

describe("Deals in the Review Center", () => {
  it("the deals tab lists deals to decide and open duplicate candidates", async () => {
    renderWithIntl(<DealQueue status="needs_review" page={1} onChange={() => {}} />, "fr");
    expect(await screen.findByTestId("deal-table")).toBeTruthy();
    const dup = await screen.findByTestId("dq-deal-duplicate");
    expect(dup.textContent).toMatch(/Doublon potentiel/);
    expect(screen.getAllByTestId("deal-open")[0].getAttribute("href")).toBe("/data-quality/deals/deal-1");
  });

  it("a decision goes through the backend with the state the reviewer saw", async () => {
    renderWithIntl(<DealReviewPage params={params("deal-1")} />, "en");
    await screen.findByTestId("dq-actions");
    fireEvent.change(within(screen.getByTestId("dq-actions")).getByPlaceholderText("e.g. analyst-1"), { target: { value: " analyst-2 " } });
    fireEvent.change(within(screen.getByTestId("dq-actions")).getByPlaceholderText(/Why this decision/), { target: { value: "Checked p.3" } });
    fireEvent.click(screen.getByTestId("dq-action-review"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("dq-confirm-yes"));
    });
    expect(state.posts).toEqual([{ id: "deal-1", action: "review", body: {
      actor: "analyst-2", reason: "Checked p.3", expected_status: "needs_review", expected_updated_at: "2026-09-01T10:00:00.123456Z" } }]);
    await waitFor(() => expect(screen.getByTestId("dq-done")).toBeTruthy()); // stays visible after the reload
  });

  it("verify is not offered by the backend while a candidate is open; a 409 is explained", async () => {
    state.deal = detail({ status: "reviewed", allowed_actions: ["review", "reject"], duplicates: [candidate()] });
    state.postError = 409;
    renderWithIntl(<DealReviewPage params={params("deal-1")} />, "en");
    await screen.findByTestId("dq-actions");
    expect((screen.getByTestId("dq-action-verify") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("deal-open-duplicates")).toBeTruthy();
    fireEvent.change(within(screen.getByTestId("dq-actions")).getByPlaceholderText("e.g. analyst-1"), { target: { value: "a" } });
    fireEvent.change(within(screen.getByTestId("dq-actions")).getByPlaceholderText(/Why this decision/), { target: { value: "r" } });
    fireEvent.click(screen.getByTestId("dq-action-reject"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("dq-confirm-yes"));
    });
    expect(await screen.findByTestId("dq-error")).toBeTruthy();
  });

  it("a duplicate decision requires identifier, reason and confirmation; never automatic", async () => {
    state.deal = detail({ duplicates: [candidate()] });
    renderWithIntl(<DealReviewPage params={params("deal-1")} />, "en");
    const form = await screen.findByTestId("dup-decide");
    expect((within(form).getByTestId("dup-submit") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(form).getByTestId("dup-decision"), { target: { value: "same_deal" } });
    fireEvent.change(within(form).getByTestId("dup-actor"), { target: { value: "analyst-3" } });
    fireEvent.change(within(form).getByTestId("dup-reason"), { target: { value: "Same signing" } });
    fireEvent.click(within(form).getByTestId("dup-submit"));
    expect(state.decisions).toEqual([]);
    await act(async () => {
      fireEvent.click(within(form).getByTestId("dup-confirm-yes"));
    });
    expect(state.decisions).toEqual([{ id: "cand-1", body: {
      decision: "same_deal", primary_deal_id: "deal-1", actor: "analyst-3", reason: "Same signing" } }]);
  });
});
