/** Phase 21 — automatic validation panel: every check shown, a human can withdraw the decision. */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { AutoValidation } from "@/types";
import { renderWithIntl } from "./helpers";

const state = vi.hoisted(() => ({ posts: [] as unknown[] }));
vi.mock("@/lib/api", () => ({
  postRevokeAutomatic: (...args: unknown[]) => {
    state.posts.push(args);
    return Promise.resolve({});
  },
}));

import { AutoValidationPanel } from "@/components/data-quality/AutoValidationPanel";

const report: AutoValidation = {
  ruleset: "auto-v1", checked_at: "2026-10-06T12:00:00Z", outcome: "verified",
  checks: [
    { check: "source_text", result: "pass", detail: "'1 234 567' on p.1" },
    { check: "time_series", result: "skip", detail: "no adjacent year" },
    { check: "corroboration", result: "pass", detail: "document d2 p.1" },
  ],
};

beforeEach(() => {
  state.posts = [];
});

describe("Automatic validation panel", () => {
  it("lists every check and lets a human withdraw the decision with identifier and reason", async () => {
    const onDone = vi.fn();
    renderWithIntl(<AutoValidationPanel kind="observation" id="fd-1" status="verified" method="automatic"
                                        report={report} blocked={false} onDone={onDone} />, "fr");
    expect(screen.getByTestId("auto-validation-headline").textContent).toMatch(/Vérifiée automatiquement/);
    expect(screen.getByTestId("auto-check-source_text").textContent).toMatch(/réussi · Valeur relue sur la page/);
    expect(screen.getByTestId("auto-check-time_series").textContent).toMatch(/non applicable/);
    fireEvent.click(screen.getByTestId("auto-revoke-open"));
    const confirm = screen.getByTestId("auto-revoke-confirm") as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("auto-revoke-actor"), { target: { value: "analyst-1" } });
    fireEvent.change(screen.getByTestId("auto-revoke-reason"), { target: { value: "À relire" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(state.posts[0]).toEqual(["observation", "fd-1", { actor: "analyst-1", reason: "À relire", expected_status: "verified" }]);
  });

  it("a human decision or a withdrawn validation offers no withdrawal button", () => {
    renderWithIntl(<AutoValidationPanel kind="deal" id="d" status="needs_review" method={null}
                                        report={{ ...report, outcome: "verified", revoked_by: "analyst-1" }} blocked
                                        onDone={() => {}} />, "fr");
    expect(screen.getByTestId("auto-validation-headline").textContent).toMatch(/retirée par analyst-1/);
    expect(screen.queryByTestId("auto-revoke-open")).toBeNull();
  });

  it("nothing is shown when the robot never looked at the row", () => {
    const view = renderWithIntl(<AutoValidationPanel kind="deal" id="d" status="needs_review" method={null}
                                                     report={null} blocked={false} onDone={() => {}} />, "en");
    expect(view.container.textContent).toBe("");
  });
});
