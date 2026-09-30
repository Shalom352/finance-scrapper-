/**
 * Phase 12 — Data Quality & Review Center.
 * Counters, queue, detail, decisions: every state comes from the (mocked) backend;
 * the UI never decides a status, never converts a currency, never turns missing into 0.
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type {
  FinancialDataDetail,
  FinancialDataExplorerItem,
  ReviewCenterCounts,
  ReviewDetail,
  ReviewEvent,
  ReviewObservation,
} from "@/types";
import { renderWithIntl } from "./helpers";

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  sets: [] as Record<string, unknown>[],
  queueCalls: [] as Record<string, unknown>[],
  posts: [] as { id: string; action: string; body: Record<string, unknown> }[],
  detailCalls: [] as string[],
  provenanceCalls: [] as string[],
  queue: null as unknown,
  detail: null as unknown,
  history: [] as unknown[],
  postError: null as number | null,
  detailError: null as number | null,
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
    getDataQualityQueue: (p: Record<string, unknown>) => {
      state.queueCalls.push(p);
      return Promise.resolve(state.queue);
    },
    getDataQualityCounts: () => Promise.resolve(counts),
    getFinancialDataFacets: () =>
      Promise.resolve({ period_years: [2024], period_types: ["annual", "semi_annual"], scopes: ["consolidated", "individual"],
        currencies: ["EUR", "XOF"], statuses: ["extracted", "needs_review", "rejected", "verified"], metric_codes: ["capitaux_propres"] }),
    getInstitutionsAll: () => Promise.resolve([]),
    getReviewDetail: (id: string) => {
      state.detailCalls.push(id);
      return state.detailError ? Promise.reject(new ApiError(state.detailError, "x")) : Promise.resolve(state.detail);
    },
    getReviewHistory: () => Promise.resolve(state.history),
    postReviewAction: (id: string, action: string, body: Record<string, unknown>) => {
      state.posts.push({ id, action, body });
      return state.postError ? Promise.reject(new ApiError(state.postError, "x")) : Promise.resolve({});
    },
    getFinancialDataById: (id: string) => {
      state.provenanceCalls.push(id);
      return new Promise(() => {});
    },
  };
});

import DataQualityPage from "@/app/[locale]/data-quality/page";
import ReviewDetailPage from "@/app/[locale]/data-quality/[dataId]/page";

const counts: ReviewCenterCounts = {
  total: 10, extracted: 6, needs_review: 1, reviewed: 1, verified: 1, rejected: 1,
  conflict_keys: 2, conflict_observations: 4, unresolved: 5,
};

const item = (over: Partial<FinancialDataExplorerItem> = {}): FinancialDataExplorerItem => ({
  id: "fd-100", institution_id: "A", institution_name: "Banque A", country_code: "CI", metric_code: "capitaux_propres",
  scope: "individual", period_type: "annual", period_year: 2024, period_label: null, value_original: "100",
  unit_original: "unit", currency_original: "XOF", value_normalized: 100, unit_normalized: "unit",
  currency_normalized: "XOF", extraction_method: "pdf_table", status: "extracted", source_id: "s", source_name: "BCEAO",
  document_id: "doc", document_title: "Rapport annuel A", page_number: 12, qualification: "conflict",
  authoritative_data_id: null, ...over,
});

const observation = (over: Partial<FinancialDataDetail> = {}): FinancialDataDetail => ({
  ...item(), confidence_score: null, notes: null, extracted_at: null, verified_at: null, verified_by: null,
  created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-02T10:00:00.123456Z",
  institution: { id: "A", name_official: "Banque A", institution_type: "bank", country_id: "ci", status: "active" },
  source: { id: "s", name: "BCEAO" } as FinancialDataDetail["source"],
  document: { id: "doc", title: "Rapport annuel A" } as FinancialDataDetail["document"],
  metric: null, source_id: "s", document_id: "doc", page_number: 12, ...over,
} as FinancialDataDetail);

const competing = (over: Partial<ReviewObservation>): ReviewObservation => ({
  id: "fd-100", status: "extracted", qualification: "conflict", scope: "individual", period_type: "annual",
  period_year: 2024, value_original: "100", value_normalized: 100, unit_normalized: "unit", currency_normalized: "XOF",
  extraction_method: "pdf_table", source_name: "BCEAO", document_title: "Rapport annuel A", page_number: 12,
  difference: null, difference_reason: "same_observation", ...over,
});

const conflictDetail = (over: Partial<ReviewDetail> = {}): ReviewDetail => ({
  observation: observation(),
  country_code: "CI",
  qualification: "conflict",
  authoritative_data_id: null,
  allowed_actions: ["review", "reject"],
  competing: [
    competing({}),
    competing({ id: "fd-130", value_normalized: 130, page_number: 30, difference: 30, difference_reason: null }),
    competing({ id: "fd-eur", value_normalized: 0.5, currency_normalized: "EUR", difference: null, difference_reason: "currency_mismatch" }),
  ],
  not_comparable: [competing({ id: "fd-cons", scope: "consolidated", value_normalized: 900, difference_reason: null, qualification: "authoritative" })],
  ...over,
});

const event: ReviewEvent = {
  id: "e1", financial_data_id: "fd-100", action: "review", previous_status: "extracted", new_status: "reviewed",
  reason: "Read on p.12", actor: "analyst-1", value_before: 100, value_after: 100, created_at: "2026-09-03T10:00:00Z",
};

const page = (items: FinancialDataExplorerItem[]) => ({ items, total: items.length, page: 1, page_size: 25, has_next: false, has_prev: false });

async function renderDetail(locale: "fr" | "en" = "fr") {
  const view = renderWithIntl(<ReviewDetailPage params={Object.assign(Promise.resolve({ dataId: "fd-100", locale }), { status: "fulfilled", value: { dataId: "fd-100", locale } })} />, locale);
  await waitFor(() => expect(screen.queryByTestId("dq-facts") ?? screen.queryByRole("heading", { level: 3 })).toBeTruthy());
  return view;
}

function fill(actor = "analyst-1", reason = "Checked on p.12") {
  fireEvent.change(screen.getByLabelText(/identifiant|identifier/i), { target: { value: actor } });
  fireEvent.change(screen.getByLabelText(/motif|reason/i), { target: { value: reason } });
}

beforeEach(() => {
  state.params = new URLSearchParams();
  state.sets = [];
  state.queueCalls = [];
  state.posts = [];
  state.detailCalls = [];
  state.provenanceCalls = [];
  state.queue = page([item(), item({ id: "fd-nr", status: "needs_review", qualification: "needs_review", metric_code: "total_actifs" })]);
  state.detail = conflictDetail();
  state.history = [];
  state.postError = null;
  state.detailError = null;
});

describe("queue", () => {
  it("shows counters only (no rate, no score) and the rows to decide", async () => {
    renderWithIntl(<DataQualityPage />);
    await screen.findByTestId("dq-counts");
    expect(within(screen.getByTestId("dq-count-unresolved")).getByText("5")).toBeTruthy();
    expect(screen.getByTestId("dq-counts").textContent).not.toMatch(/%|score|\/100/i);
    await screen.findByTestId("explorer-table");
    expect(screen.getAllByTestId("explorer-row")).toHaveLength(2);
  });

  it("does not force a period type or scope and defaults to the rows needing a decision", async () => {
    renderWithIntl(<DataQualityPage />);
    await screen.findByTestId("explorer-table");
    const call = state.queueCalls.at(-1)!;
    expect(call.period_type).toBeUndefined();
    expect(call.scope).toBeUndefined();
    expect(call.status).toBeUndefined();
    const status = screen.getByLabelText("Statut") as HTMLSelectElement;
    expect(status.options[0].text).toBe("À traiter (à réviser + valeurs divergentes)");
  });

  it("filters are URL state and travel to the detail link", async () => {
    state.params = new URLSearchParams("status=rejected&country=CI&page=2");
    renderWithIntl(<DataQualityPage />);
    await screen.findByTestId("explorer-table");
    expect(state.queueCalls.at(-1)).toMatchObject({ status: "rejected", country_code: "CI", page: 2 });
    expect(screen.getAllByTestId("row-link")[0].getAttribute("href")).toBe("/data-quality/fd-100?status=rejected&country=CI&page=2");
    fireEvent.change(screen.getByLabelText("Statut"), { target: { value: "verified" } });
    expect(state.sets.at(-1)).toEqual({ status: "verified", page: null });
  });

  it("empty queue", async () => {
    state.queue = page([]);
    renderWithIntl(<DataQualityPage />, "en");
    expect(await screen.findByText("No observation to decide")).toBeTruthy();
  });
});

describe("detail", () => {
  it("shows every observation field, provenance and the back link with the queue filters", async () => {
    state.params = new URLSearchParams("status=needs_review");
    await renderDetail();
    const facts = screen.getByTestId("dq-facts").textContent ?? "";
    for (const text of ["fd-100", "Banque A", "Côte d'Ivoire", "100 unit XOF", "FCFA", "Rapport annuel A", "BCEAO", "pdf_table", "Valeurs divergentes non résolues"])
      expect(facts).toContain(text);
    expect(screen.getByTestId("dq-back").getAttribute("href")).toBe("/data-quality?status=needs_review");
    fireEvent.click(screen.getByTestId("dq-provenance"));
    expect(state.provenanceCalls).toEqual(["fd-100"]);
  });

  it("conflict: side by side, difference only in the same currency, other scope listed apart", async () => {
    await renderDetail();
    expect(screen.getByTestId("dq-conflict-guide")).toBeTruthy();
    const diffs = screen.getAllByTestId("dq-difference").map((c) => c.textContent);
    expect(diffs).toEqual(["—", "+30", "Non comparable : devises différentes"]);
    const other = screen.getByTestId("dq-not-comparable");
    expect(other.textContent).toContain("900");
    expect(within(other).queryByTestId("dq-difference")).toBeNull();
  });

  it("a missing value is shown as missing, never 0", async () => {
    state.detail = conflictDetail({
      observation: observation({ value_normalized: null }), qualification: "missing_value", allowed_actions: ["reject"],
      competing: [competing({ value_normalized: null })], not_comparable: [],
    });
    await renderDetail();
    expect(screen.getByTestId("dq-facts").textContent).toContain("Donnée non renseignée");
    expect(screen.queryByTestId("dq-conflict-guide")).toBeNull();
  });

  it("404 → not found state", async () => {
    state.detailError = 404;
    await renderDetail();
    expect(screen.getByText("Observation introuvable.")).toBeTruthy();
  });

  it("history lists the traced decisions", async () => {
    state.history = [event, { ...event, id: "e2", action: "reject", previous_status: "reviewed", new_status: "rejected", actor: null, reason: "Wrong column", value_before: 100, value_after: 100 }];
    await renderDetail();
    const items = screen.getAllByTestId("dq-history-item").map((li) => li.textContent);
    expect(items[0]).toContain("Revue");
    expect(items[0]).toContain("par analyst-1");
    expect(items[0]).toContain("Read on p.12");
    expect(items[1]).toContain("identifiant non renseigné");
  });
});

describe("review actions", () => {
  it("only allowed actions are enabled, and only once identifier + reason are filled", async () => {
    await renderDetail();
    const btn = (a: string) => screen.getByTestId(`dq-action-${a}`) as HTMLButtonElement;
    expect([btn("review").disabled, btn("verify").disabled, btn("reject").disabled]).toEqual([true, true, true]);
    fill();
    expect([btn("review").disabled, btn("verify").disabled, btn("reject").disabled]).toEqual([false, true, false]);
  });

  it("no action for a rejected observation", async () => {
    state.detail = conflictDetail({ observation: observation({ status: "rejected" }), allowed_actions: [], qualification: "rejected" });
    await renderDetail();
    expect(screen.getByTestId("dq-no-action")).toBeTruthy();
  });

  it("asks for confirmation, then sends the decision with the state seen (never a status)", async () => {
    await renderDetail();
    fill();
    fireEvent.click(screen.getByTestId("dq-action-reject"));
    expect(screen.getByTestId("dq-confirm").textContent).toContain("Êtes-vous sûr de vouloir rejeter cette observation ?");
    expect(state.posts).toEqual([]);
    fireEvent.click(screen.getByTestId("dq-confirm-no"));
    expect(screen.queryByTestId("dq-confirm")).toBeNull();
    fireEvent.click(screen.getByTestId("dq-action-reject"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("dq-confirm-yes"));
    });
    expect(state.posts).toEqual([{
      id: "fd-100", action: "reject",
      body: { actor: "analyst-1", reason: "Checked on p.12", expected_status: "extracted", expected_updated_at: "2026-09-02T10:00:00.123456Z" },
    }]);
    expect(JSON.stringify(state.posts[0].body)).not.toMatch(/new_status|"status"/);
    await waitFor(() => expect(state.detailCalls.length).toBeGreaterThan(1)); // reloaded after the decision
  });

  it.each([
    [409, "L'observation a été modifiée par un autre reviewer. Rechargez avant de décider."],
    [422, "Transition impossible depuis le statut actuel, ou champ manquant."],
    [404, "Observation introuvable : elle a peut-être été supprimée."],
    [500, "Erreur serveur : la décision n'a pas été enregistrée."],
  ])("error %s is shown explicitly", async (status, message) => {
    state.postError = status;
    await renderDetail();
    fill();
    fireEvent.click(screen.getByTestId("dq-action-review"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("dq-confirm-yes"));
    });
    expect(screen.getByTestId("dq-error").textContent).toContain(message);
    expect(!!screen.queryByTestId("dq-reload")).toBe(status === 409);
  });
});

describe("FR / EN", () => {
  it("English detail has no French text", async () => {
    state.history = [event];
    await renderDetail("en");
    const text = document.body.textContent ?? "";
    expect(text).toContain("Competing observations");
    expect(text).toContain("Not comparable: different currencies");
    expect(text).toContain("Decision history");
    for (const fr of ["Valeur", "Périmètre", "Devise", "Observations concurrentes", "Motif", "Rejeter", "identifiant", "Revue"])
      expect(text).not.toContain(fr);
  });
});
