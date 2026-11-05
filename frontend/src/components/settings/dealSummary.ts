type SummaryRow = Record<string, unknown>;
const COUNT_KEYS = ["deals_created", "deals_enriched", "fields_enriched", "already_imported", "already_imported_tranches"];

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function sourceDealSummaries(value: Record<string, unknown> | null | undefined): [string, SummaryRow][] {
  if (!value) return [];
  return Object.entries(value)
    .filter(([key, item]) => !key.startsWith("_") && item !== null && typeof item === "object" && !Array.isArray(item))
    .map(([key, item]) => [key, item as SummaryRow] as [string, SummaryRow]);
}

export function dealCollectionTotals(value: Record<string, unknown> | null | undefined) {
  const rows = sourceDealSummaries(value).filter(([, row]) =>
    COUNT_KEYS.some((key) => typeof row[key] === "number" && Number.isFinite(row[key]))
  );
  if (rows.length === 0) return { available: false, created: 0, enriched: 0, fields: 0, known: 0 };
  return rows.reduce((totals, [, row]) => ({
    available: true,
    created: totals.created + count(row.deals_created),
    enriched: totals.enriched + count(row.deals_enriched),
    fields: totals.fields + count(row.fields_enriched),
    known: totals.known + count(row.already_imported ?? row.already_imported_tranches),
  }), { available: false, created: 0, enriched: 0, fields: 0, known: 0 });
}
