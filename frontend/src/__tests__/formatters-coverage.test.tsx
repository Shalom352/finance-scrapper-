/**
 * Test 1 — coverage is never invented; formatting follows the locale.
 */
import React from "react";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import {
  MISSING,
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatPercent,
  formatSignedPercent,
} from "@/lib/formatters";
import { renderWithIntl } from "./helpers";

const NBSP = " ";

describe("Test 1 — coverage indicator", () => {
  it("coverage absent → —", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={undefined} />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(MISSING);
  });

  it("coverage null → —", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={null} />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(MISSING);
  });

  it("coverage 0 → 0 %", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={0} />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(`0,0${NBSP}%`);
  });

  it("coverage 0.82 → 82 %", () => {
    renderWithIntl(<CoverageIndicator coverageRatio={0.82} />);
    expect(screen.getByTestId("coverage-value").textContent).toBe(`82,0${NBSP}%`);
  });

  it("never shows 85 % when coverage is unknown", () => {
    const { container } = renderWithIntl(<CoverageIndicator coverageRatio={null} isPartial={null} />);
    expect(container.textContent).not.toContain("85");
  });

  it("the partial warning only comes from the backend is_partial flag", () => {
    const { container, rerender } = renderWithIntl(<CoverageIndicator coverageRatio={0.5} isPartial={false} />);
    expect(container.textContent).not.toMatch(/partielles/);
    rerender(<></>);
    renderWithIntl(<CoverageIndicator coverageRatio={0.5} isPartial={true} />);
    expect(screen.getByText(/Données partielles/)).toBeTruthy();
  });
});

describe("formatters", () => {
  it("missing values render as — (never 0, N/A or a currency)", () => {
    for (const v of [null, undefined, Number.NaN]) {
      expect(formatCurrency(v, "XOF")).toBe(MISSING);
      expect(formatCompactCurrency(v, "XOF")).toBe(MISSING);
      expect(formatPercent(v)).toBe(MISSING);
      expect(formatSignedPercent(v)).toBe(MISSING);
    }
    expect(formatDate(null)).toBe(MISSING);
    expect(formatDate("not-a-date")).toBe(MISSING);
  });

  it("zero is a real value, not missing", () => {
    expect(formatPercent(0)).toBe(`0,00${NBSP}%`);
  });

  it("XOF is displayed as FCFA with non-breaking spaces and French decimals", () => {
    expect(formatCompactCurrency(3_450_000_000, "XOF", "fr")).toBe(`3,45${NBSP}Md${NBSP}FCFA`);
    expect(formatCompactCurrency(12_500_000, "XOF", "fr")).toBe(`12,50${NBSP}M${NBSP}FCFA`);
    expect(formatCompactCurrency(-3_450_000_000, "XOF", "fr")).toBe(`-3,45${NBSP}Md${NBSP}FCFA`);
  });

  it("English locale uses a dot and bn", () => {
    expect(formatCompactCurrency(3_450_000_000, "XOF", "en")).toBe(`3.45${NBSP}bn${NBSP}FCFA`);
    expect(formatPercent(3.456, "en")).toBe("3.46%");
  });

  it("an unknown currency is not guessed", () => {
    expect(formatCurrency(1000, null, "fr")).not.toContain("FCFA");
    expect(formatCurrency(1000, "EUR", "fr")).toContain("EUR");
  });

  it("dates: fr DD/MM/YYYY, en MM/DD/YYYY", () => {
    expect(formatDate("2024-03-05T12:00:00Z", "fr")).toBe("05/03/2024");
    expect(formatDate("2024-03-05T12:00:00Z", "en")).toBe("03/05/2024");
  });
});
