/**
 * Phase 20 — targeting: explicit criteria with evidence, no score, nothing guessed from the URL.
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import type { TargetingResponse } from "@/types";
import { parseTargetingParams } from "@/lib/targeting";
import { renderWithIntl } from "./helpers";

const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  sets: [] as Record<string, unknown>[],
  calls: [] as Record<string, unknown>[],
  response: null as unknown,
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
    <a href={href} {...rest}>{children}</a>
  ),
}));
vi.mock("@/lib/api", () => ({
  getTargeting: (q: Record<string, unknown>) => {
    state.calls.push(q);
    return Promise.resolve(state.response);
  },
}));

import TargetingPage from "@/app/[locale]/targeting/page";

const response: TargetingResponse = {
  request: {}, method: "…", total: 2,
  items: [
    { kind: "bank", id: "b1", name: "BANQUE TOGO", country_code: "TG", entity_type: null, website: null,
      criteria_met: 1, criteria_known: 2,
      criteria: {
        presence: { status: "not_met", country: "TG" },
        experience: { status: "met", financing_deals: 1, comparable_deals: 1, to_confirm: 1,
          deals: [{ deal_id: "d1", title: "Centrale solaire CI", roles: ["lender"], matches: ["sector", "country"],
                    year: 2025, amount: null, unit: null, currency: null, status: "needs_review" }] },
        capacity: { status: "unknown", reason: "equity_not_available" },
        relationship: { status: "unknown", reason: "no_contact_recorded" },
      } },
    { kind: "institution", id: "e1", name: "Banque Ouest Africaine de Développement", country_code: "TG",
      entity_type: "development_bank", website: "https://www.boad.org", criteria_met: 0, criteria_known: 0,
      criteria: { capacity: { status: "unknown", reason: "not_applicable_institution" } } },
  ],
};

beforeEach(() => {
  state.params = new URLSearchParams();
  state.sets = [];
  state.calls = [];
  state.response = response;
});

describe("Targeting", () => {
  it("asks for a deal profile before searching", () => {
    renderWithIntl(<TargetingPage />, "fr");
    expect(screen.getByText("Décrivez la transaction")).toBeTruthy();
    expect(state.calls).toEqual([]);
  });

  it("drops invalid URL values instead of guessing", () => {
    const q = parseTargetingParams((k) => ({ country: "FR", sector: "energy", amount: "-5", currency: "XAF", deal_type: "x" } as Record<string, string>)[k] ?? "");
    expect(q).toEqual({ country: undefined, sector: "energy", deal_type: undefined, amount: undefined, currency: undefined, kind: undefined });
  });

  it("shows each criterion with its status and evidence, never a score", async () => {
    state.params = new URLSearchParams("country=CI&sector=energy&amount=20000000000&currency=XOF");
    const view = renderWithIntl(<TargetingPage />, "fr");
    const cards = await screen.findAllByTestId("targeting-candidate");
    expect(state.calls[0]).toMatchObject({ country: "CI", sector: "energy", amount: 20000000000, currency: "XOF" });
    const bank = cards[0];
    expect(within(bank).getByTestId("criterion-presence").getAttribute("data-status")).toBe("not_met");
    expect(within(bank).getByTestId("criterion-experience").textContent).toMatch(/Expérience · oui/);
    expect(bank.textContent).toMatch(/Centrale solaire CI/);
    expect(bank.textContent).toMatch(/même secteur \+ même pays/);
    expect(bank.textContent).toMatch(/à confirmer/);
    expect(bank.textContent).toMatch(/Capitaux propres publiés non disponibles/);
    expect(cards[1].textContent).toMatch(/Institution de financement/);
    expect(view.container.textContent).not.toMatch(/recommand|meilleur|score\s*[:=]?\s*\d/i);
  });

  it("changing a filter writes the URL", () => {
    state.params = new URLSearchParams("country=CI");
    renderWithIntl(<TargetingPage />, "fr");
    fireEvent.change(screen.getByTestId("targeting-sector"), { target: { value: "agriculture" } });
    expect(state.sets).toContainEqual({ sector: "agriculture" });
  });
});
