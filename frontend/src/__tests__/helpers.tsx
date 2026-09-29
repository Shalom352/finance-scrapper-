import React from "react";
import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import fr from "@/messages/fr.json";
import en from "@/messages/en.json";
import type { FinancialDataPoint } from "@/types";

export function renderWithIntl(ui: React.ReactElement, locale: "fr" | "en" = "fr") {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === "fr" ? fr : en} timeZone="UTC">
      {ui}
    </NextIntlClientProvider>,
  );
}

let seq = 0;

/** Minimal list-row fixture (backend FinancialDataList). */
export function point(overrides: Partial<FinancialDataPoint> = {}): FinancialDataPoint {
  seq += 1;
  return {
    id: `fd-${seq}`,
    institution_id: "inst-1",
    metric_code: "total_actifs",
    scope: "individual",
    period_type: "annual",
    period_year: 2023,
    period_label: null,
    value_original: "100",
    unit_original: null,
    currency_original: "XOF",
    value_normalized: 100,
    unit_normalized: "unit",
    currency_normalized: "XOF",
    extraction_method: "pdf_table",
    status: "extracted",
    ...overrides,
  };
}
