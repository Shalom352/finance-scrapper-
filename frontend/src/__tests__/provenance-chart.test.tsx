/**
 * Test 7 — the provenance panel loads the real financial data record.
 * Plus: the line chart renders a gap for a missing year.
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { FinancialDataDetail } from "@/types";
import { MISSING } from "@/lib/formatters";
import { renderWithIntl, point } from "./helpers";

// Plain function (not a vi.fn spy): spy result tracking reports rejected promises as unhandled.
const api = vi.hoisted(() => ({
  calls: [] as string[],
  impl: (() => Promise.reject(new Error("not configured"))) as (id: string) => Promise<unknown>,
}));
vi.mock("@/lib/api", () => ({
  getFinancialDataById: (id: string) => {
    api.calls.push(id);
    return api.impl(id);
  },
}));

import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { FinancialLineChart } from "@/components/charts/FinancialLineChart";


function detail(overrides: Partial<FinancialDataDetail> = {}): FinancialDataDetail {
  return {
    ...point({ id: "fd-42", value_normalized: 3_450_000_000_000, value_original: "3 450 000", unit_original: "millions" }),
    source_id: "src-1",
    document_id: "doc-1",
    page_number: 42,
    confidence_score: 0.95,
    notes: null,
    extracted_at: "2024-05-01T00:00:00Z",
    verified_at: null,
    verified_by: null,
    created_at: "2024-05-01T00:00:00Z",
    updated_at: "2024-05-01T00:00:00Z",
    institution: null,
    source: { id: "src-1", name: "Rapport annuel SGCI", source_type: "bank", priority: 1, is_active: true },
    document: {
      id: "doc-1",
      title: "Rapport Annuel 2023",
      document_type: "annual_report",
      source_id: "src-1",
      download_status: "downloaded",
      extraction_status: "extracted",
    },
    metric: null,
    ...overrides,
  };
}

describe("Test 7 — provenance panel", () => {
  beforeEach(() => {
    api.calls = [];
  });

  it("loads the record by id and displays page, document and source", async () => {
    api.impl = () => Promise.resolve(detail());
    renderWithIntl(<ProvenancePanel dataId="fd-42" onClose={() => {}} />);

    expect(api.calls).toEqual(["fd-42"]);
    await waitFor(() => expect(screen.getByTestId("prov-page").textContent).toBe("42"));
    expect(screen.getByTestId("prov-document").textContent).toContain("Rapport Annuel 2023");
    expect(screen.getByTestId("prov-source").textContent).toBe("Rapport annuel SGCI");
    expect(screen.getByTestId("prov-confidence").textContent).toBe("95,0 %");
    expect(screen.getByTestId("prov-original").textContent).toContain("3 450 000");
  });

  it("missing provenance fields render as —, nothing is reconstructed", async () => {
    api.impl = () => Promise.resolve(detail({ page_number: null, source: null, document: null, confidence_score: null }));
    renderWithIntl(<ProvenancePanel dataId="fd-42" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByTestId("prov-page").textContent).toBe(MISSING));
    expect(screen.getByTestId("prov-source").textContent).toBe(MISSING);
    expect(screen.getByTestId("prov-document").textContent).toBe(MISSING);
    expect(screen.getByTestId("prov-confidence").textContent).toBe(MISSING);
  });

  it("an API failure is shown as an error, not as empty provenance", async () => {
    api.impl = () => Promise.reject(new Error("500"));
    renderWithIntl(<ProvenancePanel dataId="fd-42" onClose={() => {}} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });
});

describe("line chart — missing year", () => {
  it("draws two segments and marks 2022 as missing", () => {
    const { container } = renderWithIntl(
      <FinancialLineChart
        data={[
          { year: 2020, value: 100 },
          { year: 2021, value: 120 },
          { year: 2022, value: null },
          { year: 2023, value: 150 },
        ]}
        currency="XOF"
      />,
    );
    expect(container.querySelectorAll('[data-testid="line-segment"]')).toHaveLength(2);
    const missing = container.querySelectorAll('[data-testid="missing-year"]');
    expect(missing).toHaveLength(1);
    expect(missing[0].textContent).toContain("2022");
  });
});
