"use client";

import React, { Suspense, useEffect, useState, use } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type {
  Document,
  Institution,
  InstitutionFinancials,
  InstitutionGrowth,
  InstitutionHistory,
  InstitutionProfileCoverage,
  InstitutionRatios,
} from "@/types";
import {
  getDocuments,
  getInstitutionById,
  getInstitutionCoverage,
  getInstitutionFinancials,
  getInstitutionGrowth,
  getInstitutionHistory,
  getInstitutionRatios,
} from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useLabels } from "@/lib/useLabels";
import { useQueryParams } from "@/lib/useQueryParams";
import { DATA_SCOPES, PERIOD_TYPES, pick } from "@/lib/rankings";
import { parseYearParam } from "@/lib/url";
import { StateBadge } from "@/components/common/StatusBadge";
import { CardSkeleton, TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { FinancialDataTable } from "@/components/tables/FinancialDataTable";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { DocumentsTable } from "@/components/tables/DocumentsTable";
import { KeyFinancials } from "@/components/institutions/KeyFinancials";
import { HistoryCharts } from "@/components/institutions/HistoryCharts";
import { GrowthTable } from "@/components/institutions/GrowthTable";
import { CoveragePanel } from "@/components/institutions/CoveragePanel";
import { SourcesList } from "@/components/institutions/SourcesList";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

interface PageProps {
  params: Promise<{ id: string; locale: string }>;
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

interface Profile {
  financials: InstitutionFinancials;
  history: InstitutionHistory;
  ratios: InstitutionRatios;
  growth: InstitutionGrowth;
  coverage: InstitutionProfileCoverage;
}

const selectCls =
  "mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none";

export default function InstitutionDetailPage({ params }: PageProps) {
  const { id } = use(params);
  return (
    <Suspense fallback={<CardSkeleton />}>
      <InstitutionExplorer id={id} />
    </Suspense>
  );
}

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId?: string }) {
  return (
    <section className="space-y-3" data-testid={testId}>
      <h2 className="text-lg font-bold text-white tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

/**
 * Financial Intelligence Explorer — every value, series, ratio, change and coverage
 * figure is qualified by the backend (GET /api/v1/institutions/{id}/…). The page
 * never selects, filters or computes a financial value itself.
 */
function InstitutionExplorer({ id }: { id: string }) {
  const t = useTranslations("explorer");
  const tInst = useTranslations("institution_status");
  const labels = useLabels();
  const reason = useReasonLabel();
  const { get, set } = useQueryParams();

  // One period type and one scope at a time (defaults annual + individual), kept in the URL.
  const scope = pick(get("scope"), DATA_SCOPES, "individual");
  const period = pick(get("period"), PERIOD_TYPES, "annual");
  const year = parseYearParam(get("year"));

  const [institution, setInstitution] = useState<Load<Institution | null>>({ status: "loading" });
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [profile, setProfile] = useState<Load<Profile>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [institutionAttempt, setInstitutionAttempt] = useState(0);
  const [provenanceId, setProvenanceId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getInstitutionById(id)
      .then((data) => !cancelled && setInstitution({ status: "ready", data }))
      // Only a 404 means "not found"; any other failure is an error state with a retry.
      .catch((err: { status?: number }) =>
        !cancelled && setInstitution(err?.status === 404 ? { status: "ready", data: null } : { status: "error" }),
      );
    getDocuments({ institution_id: id, page_size: 100 })
      .then((r) => !cancelled && setDocuments(r.items))
      .catch(() => !cancelled && setDocuments(null));
    return () => {
      cancelled = true;
    };
  }, [id, institutionAttempt]);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setProfile({ status: "loading" });
    const sel = { period_type: period, data_scope: scope };
    const yearSel = { ...sel, period_year: year ?? undefined };
    Promise.all([
      getInstitutionFinancials(id, yearSel),
      getInstitutionHistory(id, sel),
      getInstitutionRatios(id, yearSel),
      getInstitutionGrowth(id, yearSel),
      getInstitutionCoverage(id, sel),
    ])
      .then(([financials, history, ratios, growth, coverage]) => {
        if (!cancelled) setProfile({ status: "ready", data: { financials, history, ratios, growth, coverage } });
      })
      .catch(() => !cancelled && setProfile({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [id, scope, period, year, attempt]);

  if (institution.status === "loading") {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={6} cols={4} />
      </div>
    );
  }
  if (institution.status === "error") {
    return <ErrorState onRetry={() => { setInstitution({ status: "loading" }); setInstitutionAttempt((n) => n + 1); }} />;
  }
  const inst = institution.status === "ready" ? institution.data : null;
  if (!inst) {
    return <EmptyState title={t("not_found_title")} description={t("not_found")} />;
  }

  const data = profile.status === "ready" ? profile.data : null;
  const selection = data?.financials.selection;
  const displayYear = data?.financials.period_year ?? null;

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <Link href="/institutions" className="inline-flex text-xs font-semibold text-gray-400 hover:text-emerald-400 transition-colors">
        ← {t("back")}
      </Link>

      {/* Institution header */}
      <header className="p-6 md:p-8 rounded-3xl border border-gray-800 bg-gray-900/40" data-testid="institution-header">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span
            data-testid="country-badge"
            className="px-2.5 py-0.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 text-emerald-400 text-xs font-bold uppercase"
          >
            {inst.country?.code ?? MISSING}
          </span>
          <span className="text-xs text-gray-400 font-medium">{labels.country(inst.country, inst.country?.code)}</span>
          <span className="text-xs text-gray-500">· {labels.institutionType(inst.institution_type) || MISSING}</span>
          <StateBadge label={tInst.has(inst.status) ? tInst(inst.status) : inst.status} tone={inst.status === "active" ? "ok" : "warn"} />
        </div>
        <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight">{inst.name_official}</h1>
        {inst.name_commercial && <p className="text-sm text-emerald-400 font-medium mt-1">{inst.name_commercial}</p>}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 text-xs text-gray-400">
          <span>
            {t("group")}{t("label_sep")} <span className="text-gray-200 font-semibold">{inst.banking_group?.name ?? MISSING}</span>
          </span>
          <span>
            {t("regulatory_id")}{t("label_sep")} <span className="text-gray-200 font-mono">{inst.regulatory_id ?? MISSING}</span>
          </span>
          <Link href={`/financial-data?inst=${encodeURIComponent(inst.id)}`} className="text-emerald-400 hover:underline" data-testid="institution-financial-data-link">
            {t("financial_data_link")} →
          </Link>
          <Link href={`/deals?bank=${encodeURIComponent(inst.id)}`} className="text-emerald-400 hover:underline" data-testid="institution-deals-link">
            {t("deals_link")} →
          </Link>
          {inst.website_url && (
            <a href={inst.website_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
              {t("website")} ↗
            </a>
          )}
        </div>
      </header>

      {/* Selection: explicit scope, period type and year — never mixed, never a fallback */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40" data-testid="selectors">
        <label className="text-[11px] text-gray-400 font-medium">
          {t("scope")}
          <select value={scope} onChange={(e) => set({ scope: e.target.value, year: null })} className={selectCls} data-testid="scope-select">
            {DATA_SCOPES.map((s) => (
              <option key={s} value={s}>
                {labels.scope(s)}
                {selection && !selection.scopes.includes(s) ? ` — ${t("not_published")}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("period_type")}
          <select value={period} onChange={(e) => set({ period: e.target.value, year: null })} className={selectCls} data-testid="period-select">
            {PERIOD_TYPES.map((p) => (
              <option key={p} value={p}>
                {labels.periodType(p)}
                {selection && !selection.period_types.includes(p) ? ` — ${t("not_published")}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("fiscal_year")}
          <select value={year ?? ""} onChange={(e) => set({ year: e.target.value })} className={selectCls} data-testid="year-select">
            <option value="">{t("latest_year")}</option>
            {(selection?.years ?? []).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <p className="sm:col-span-3 text-[11px] text-gray-500">{t("selection_note")}</p>
      </div>

      {profile.status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : !data ? (
        <TableSkeleton rows={6} cols={4} />
      ) : (
        <>
          {data.financials.status === "unavailable" && (
            <div role="alert" className="p-4 rounded-2xl border border-amber-800/60 bg-amber-950/30 text-sm text-amber-200" data-testid="profile-unavailable">
              {t("selection_unavailable", { scope: labels.scope(scope), period: labels.periodType(period) })} — {reason(data.financials.reason)}
            </div>
          )}

          <KeyFinancials financials={data.financials} onProvenance={setProvenanceId} />

          <Section title={t("financials_title", { year: displayYear ?? MISSING })} testId="financials-section">
            <FinancialDataTable values={data.financials.values} unavailable={data.financials.unavailable} onProvenance={setProvenanceId} />
          </Section>

          <Section title={t("history_title")} testId="history-section">
            <HistoryCharts history={data.history} onProvenance={setProvenanceId} />
          </Section>

          <Section title={t("ratios_title")} testId="ratios-section">
            {data.ratios.status === "unavailable" && data.ratios.reason ? (
              <p className="text-xs text-gray-500">{reason(data.ratios.reason)}</p>
            ) : null}
            <RatioDataTable ratios={data.ratios.items} />
          </Section>

          <Section title={t("growth_title")} testId="growth-section">
            {data.growth.status === "unavailable" && data.growth.reason ? (
              <p className="text-xs text-gray-500">{reason(data.growth.reason)}</p>
            ) : null}
            <GrowthTable items={data.growth.items} />
          </Section>

          <Section title={t("coverage_section")} testId="coverage-section">
            <CoveragePanel coverage={data.coverage} />
          </Section>

          <Section title={t("sources_title")} testId="sources-section">
            <SourcesList documents={data.coverage.documents} />
          </Section>
        </>
      )}

      <Section title={t("documents_title")} testId="documents-section">
        {documents === null ? <ErrorState /> : <DocumentsTable documents={documents} emptyText={t("documents_empty")} />}
      </Section>

      {provenanceId && <ProvenancePanel dataId={provenanceId} onClose={() => setProvenanceId(null)} />}
    </div>
  );
}
