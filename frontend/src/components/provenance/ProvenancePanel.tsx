"use client";

import React, { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { FinancialDataDetail, ProvenanceRef, RatioResult } from "@/types";
import { StatusBadge } from "@/components/common/StatusBadge";
import { MISSING, orMissing } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { useFinancialDataDetail } from "@/lib/useFinancialDataDetail";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

/** Translated code; an unknown code is shown as received, a missing one as MISSING. */
function useCodeLabel(namespace: "provenance.methods" | "provenance.roles") {
  const t = useTranslations(namespace);
  return (code: string | null | undefined) => (code ? (t.has(code) ? t(code) : code) : MISSING);
}

interface ProvenancePanelProps {
  /** Financial data row id: the panel loads the full record from the API. */
  dataId?: string | null;
  ratioPoint?: RatioResult | null;
  /** Observations behind a derived value (ranked growth / ratio): each opens its real record. */
  sources?: ProvenanceRef[] | null;
  onClose: () => void;
}

export function ProvenancePanel({ dataId, ratioPoint, sources, onClose }: ProvenancePanelProps) {
  const t = useTranslations("provenance");
  const tc = useTranslations("common");
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  // Escape closes the dialog (keyboard users).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const hasSources = !!sources && sources.length > 0;
  if (!dataId && !ratioPoint && !hasSources) return null;
  const detailId = dataId ?? selectedSource;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="provenance-dialog-title"
    >
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-3xl border border-gray-800 bg-gray-950 p-6 md:p-8 shadow-2xl">
        <div className="flex items-start justify-between pb-4 border-b border-gray-800">
          <span id="provenance-dialog-title" className="text-emerald-400 text-sm font-semibold tracking-wide uppercase">{t("title")}</span>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            aria-label={tc("close")}
          >
            ✕
          </button>
        </div>

        {!dataId && hasSources && (
          <SourcesList sources={sources!} selected={selectedSource} onSelect={setSelectedSource} />
        )}
        {detailId && <DataPointProvenance dataId={detailId} />}
        {!detailId && !hasSources && ratioPoint && <RatioProvenance ratio={ratioPoint} />}

        <div className="mt-8 pt-4 border-t border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-white text-xs font-medium transition-colors"
          >
            {tc("close")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, testId }: { label: string; value: React.ReactNode; testId?: string }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 border-b border-gray-800/60 last:border-0">
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className="font-medium text-gray-200 text-right break-all" data-testid={testId}>
        {value}
      </span>
    </div>
  );
}

function DataPointProvenance({ dataId }: { dataId: string }) {
  const methodLabel = useCodeLabel("provenance.methods");
  const t = useTranslations("provenance");
  const tc = useTranslations("common");
  const fmt = useFormatters();
  const labels = useLabels();
  const locale = useLocale();
  const { state: detail, retry } = useFinancialDataDetail(dataId);

  if (detail.status === "error") {
    return (
      <div role="alert" className="pt-6 space-y-3 text-xs text-rose-300">
        <p>{t("error")}</p>
        <button onClick={retry} className="px-3 py-1.5 rounded-lg border border-rose-700 text-rose-200">
          {tc("retry")}
        </button>
      </div>
    );
  }

  if (detail.status !== "ready") {
    return <p className="pt-6 text-xs text-gray-400">{t("loading")}</p>;
  }

  const d: FinancialDataDetail = detail.data;
  const metricLabel = d.metric ? (locale === "en" ? d.metric.label_en : d.metric.label_fr) : labels.metric(d.metric_code);
  const period = [d.period_year, labels.periodType(d.period_type), d.period_label].filter(Boolean).join(" · ");
  const original = [d.value_original, d.unit_original, d.currency_original].filter(Boolean).join(" ");

  return (
    <div className="space-y-6 pt-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h3 id="provenance-title" className="text-xl font-bold text-white">
            {metricLabel}
          </h3>
          <StatusBadge status={d.status} />
        </div>
        <p className="text-xs text-gray-400">{orMissing(d.institution?.name_official)}</p>
      </div>

      <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs">
        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{t("value_section")}</h4>
        <Row label={t("normalized_value")} value={fmt.currency(d.value_normalized, d.currency_normalized)} testId="prov-normalized" />
        <Row label={t("normalized_unit")} value={orMissing(d.unit_normalized)} />
        <Row label={t("raw_value")} value={orMissing(original)} testId="prov-original" />
        <Row label={t("period")} value={orMissing(period)} />
        <Row label={t("scope")} value={orMissing(labels.scope(d.scope))} />
      </section>

      <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs">
        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{t("source_section")}</h4>
        <Row label={t("source")} value={orMissing(d.source?.name)} testId="prov-source" />
        <Row
          label={t("document")}
          testId="prov-document"
          value={
            d.document?.url ? (
              <a href={d.document.url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
                {orMissing(d.document.title)} ↗
              </a>
            ) : (
              orMissing(d.document?.title)
            )
          }
        />
        <Row label={t("page")} value={orMissing(d.page_number)} testId="prov-page" />
        <Row label={t("method")} value={methodLabel(d.extraction_method)} />
        <Row
          label={t("confidence")}
          value={d.confidence_score === null ? MISSING : fmt.percent(d.confidence_score * 100, 1)}
          testId="prov-confidence"
        />
        <Row label={t("extracted_at")} value={fmt.date(d.extracted_at)} />
      </section>

      <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs">
        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{t("verification_section")}</h4>
        <Row label={t("status")} value={<StatusBadge status={d.status} size="sm" />} />
        <Row label={t("validator")} value={orMissing(d.verified_by)} />
        <Row label={t("verified_at")} value={fmt.date(d.verified_at)} />
        <Row label={t("notes")} value={orMissing(d.notes)} />
      </section>
    </div>
  );
}

function RatioProvenance({ ratio }: { ratio: RatioResult }) {
  const t = useTranslations("provenance");
  const reasonLabel = useReasonLabel();
  const roleLabel = useCodeLabel("provenance.roles");
  const fmt = useFormatters();
  const labels = useLabels();

  return (
    <div className="space-y-6 pt-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h3 id="provenance-title" className="text-xl font-bold text-white">
            {ratio.ratio_name}
          </h3>
          <StatusBadge status={ratio.status} />
        </div>
        <p className="text-xs text-gray-400">
          {orMissing(ratio.period_year)} — {orMissing(ratio.institution_name)}
        </p>
      </div>

      <div className="p-5 rounded-2xl bg-gray-900/60 border border-gray-800 flex items-center justify-between gap-4">
        <div>
          <span className="text-xs text-gray-400 block mb-1">{t("calculated_value")}</span>
          <span className="text-2xl font-black text-emerald-400">{fmt.percent(ratio.value_percent, 2)}</span>
          {ratio.reason && <span className="text-xs text-amber-400 block mt-1">{reasonLabel(ratio.reason)}</span>}
        </div>
        <div className="text-right">
          <span className="text-xs text-gray-400 block mb-1">{t("formula")}</span>
          <code className="text-xs px-2.5 py-1 rounded bg-gray-950 border border-gray-800 text-emerald-300 font-mono">
            {ratio.formula_used}
          </code>
        </div>
      </div>

      <div>
        <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          {t("components_title", { count: ratio.components.length })}
        </h4>
        <div className="space-y-3">
          {ratio.components.map((comp, idx) => (
            <div key={idx} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-gray-200">{labels.metric(comp.metric_code)}</span>
                  <span className="text-gray-400">({orMissing(comp.period_year)})</span>
                  {comp.role && (
                    <span className="px-1.5 py-0.5 rounded bg-gray-800 text-[10px] text-gray-400 uppercase">{roleLabel(comp.role)}</span>
                  )}
                </div>
                <StatusBadge status={comp.status} size="sm" />
              </div>
              <div className="flex items-center justify-between pt-1">
                <span className="text-gray-400">
                  {orMissing(comp.source_name)} · {t("page")} {orMissing(comp.page_number)}
                </span>
                <span className="font-semibold text-emerald-400 text-sm">
                  {fmt.currency(comp.value_normalized, comp.currency)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SourcesList({
  sources,
  selected,
  onSelect,
}: {
  sources: ProvenanceRef[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("provenance");
  const labels = useLabels();
  return (
    <div className="pt-6 space-y-2">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
        {t("components_title", { count: sources.length })}
      </h4>
      {sources.map((src) => (
        <button
          key={src.data_id}
          onClick={() => onSelect(src.data_id)}
          data-testid="provenance-source"
          className={`w-full text-left p-3 rounded-xl border text-xs transition-colors ${
            selected === src.data_id ? "border-emerald-600 bg-emerald-950/30" : "border-gray-800 bg-gray-900/40 hover:border-gray-700"
          }`}
        >
          <span className="font-bold text-gray-200">{labels.metric(src.metric_code)}</span>{" "}
          <span className="text-gray-400">
            ({orMissing(src.period_year)} · {labels.periodType(src.period_type)} · {labels.scope(src.scope)})
          </span>
          <span className="block text-gray-500 mt-0.5">
            {orMissing(src.source_name)} · {orMissing(src.document_title)} · {t("page")} {orMissing(src.page_number)}
          </span>
        </button>
      ))}
    </div>
  );
}
