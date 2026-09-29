"use client";

import React, { Suspense, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import type { ComparisonRow, CountryComparison, Institution, InstitutionsComparison, SectorComparison } from "@/types";
import {
  getCountryComparison,
  getInstitutionsAll,
  getInstitutionsComparison,
  getSectorComparison,
} from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { UMOA_COUNTRY_CODES, isUmoaCountry } from "@/lib/countries";
import {
  DATA_SCOPES,
  MAX_COMPARED,
  MIN_COMPARED,
  PERIOD_TYPES,
  parseIds,
  parseRankingParams,
  supportsPeriodType,
} from "@/lib/rankings";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { IndicatorSelect, selectCls, useIndicatorLabel } from "@/components/rankings/IndicatorSelect";
import { ComparisonTable, CountryComparisonCard, SectorComparisonCard } from "@/components/rankings/ComparisonTable";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

const MAX_INSTITUTIONS = MAX_COMPARED;
const MIN_INSTITUTIONS = MIN_COMPARED;

export default function ComparisonsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={5} />}>
      <ComparisonsContent />
    </Suspense>
  );
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

function ComparisonsContent() {
  const t = useTranslations("comparisons");
  const tCountries = useTranslations("country_names");
  const labels = useLabels();
  const reason = useReasonLabel();
  const indicatorLabel = useIndicatorLabel();
  const { get, set } = useQueryParams();
  const p = parseRankingParams(get);
  const ids = parseIds(get("ids"));
  const idsKey = ids.join(",");

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [result, setResult] = useState<Load<InstitutionsComparison> | null>(null);
  const [sector, setSector] = useState<{ id: string; result: SectorComparison }[]>([]);
  const [country, setCountry] = useState<Load<CountryComparison> | null>(null);
  const [provenance, setProvenance] = useState<ComparisonRow | null>(null);

  useEffect(() => {
    getInstitutionsAll()
      .then(setInstitutions)
      .catch(() => setInstitutions([]));
  }, []);

  const byId = useMemo(() => new Map(institutions.map((i) => [i.id, i])), [institutions]);
  const firstCountry = ids.map((i) => byId.get(i)?.country?.code).find((c): c is string => !!c) ?? null;
  const countryParam = get("country").toUpperCase();
  const countryCode = isUmoaCountry(countryParam) ? countryParam : firstCountry;

  useEffect(() => {
    if (ids.length < MIN_INSTITUTIONS) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- nothing to compare yet
      setResult(null);
      return;
    }
    let cancelled = false;
    setResult({ status: "loading" });
    getInstitutionsComparison({
      institution_ids: ids,
      metric_code: p.metric,
      period_year: p.year ?? undefined,
      period_type: p.period,
      data_scope: p.scope,
    })
      .then((data) => !cancelled && setResult({ status: "ready", data }))
      .catch(() => !cancelled && setResult({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- idsKey is the stable form of ids
  }, [idsKey, p.metric, p.year, p.period, p.scope]);

  // Institution vs sector: individual + annual published metrics only (Phase 8C rule).
  useEffect(() => {
    if (ids.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- not applicable
      setSector([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      ids.map((id) =>
        getSectorComparison({ institution_id: id, metric_code: p.metric, period_year: p.year ?? undefined }).catch(
          () => null,
        ),
      ),
    ).then(
      (rows) =>
        !cancelled &&
        setSector(
          rows.flatMap((result, i) => (result ? [{ id: ids[i], result }] : [])),
        ),
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- idsKey is the stable form of ids
  }, [idsKey, p.metric, p.year]);

  useEffect(() => {
    if (!countryCode) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- not applicable
      setCountry(null);
      return;
    }
    let cancelled = false;
    setCountry({ status: "loading" });
    getCountryComparison({ country_code: countryCode, metric_code: p.metric, period_year: p.year ?? undefined })
      .then((data) => !cancelled && setCountry({ status: "ready", data }))
      .catch(() => !cancelled && setCountry({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [countryCode, p.metric, p.year]);

  const slots = Array.from({ length: MAX_INSTITUTIONS }, (_, i) => ids[i] ?? "");
  const setSlot = (index: number, value: string) => {
    const next = [...slots];
    next[index] = value;
    set({ ids: parseIds(next.join(",")).join(",") || null });
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {slots.map((value, i) => (
            <label key={i} className="text-[11px] text-gray-400 font-medium">
              {t("institution_n", { n: i + 1 })}
              <select value={value} onChange={(e) => setSlot(i, e.target.value)} className={selectCls}>
                <option value="">{MISSING}</option>
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id} disabled={ids.includes(inst.id) && inst.id !== value}>
                    {inst.name_official} ({inst.country?.code ?? MISSING})
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <IndicatorSelect
              label={t("metric")}
              value={p.metric}
              onChange={(metric) => set({ metric, period: supportsPeriodType(metric, p.period) ? p.period : "annual" })}
            />
          </div>
          <label className="text-[11px] text-gray-400 font-medium">
            {t("scope")}
            <select value={p.scope} onChange={(e) => set({ scope: e.target.value })} className={selectCls}>
              {DATA_SCOPES.map((s) => (
                <option key={s} value={s}>
                  {labels.scope(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] text-gray-400 font-medium">
            {t("period")}
            <select value={p.period} onChange={(e) => set({ period: e.target.value })} className={selectCls}>
              {PERIOD_TYPES.filter((pt) => supportsPeriodType(p.metric, pt)).map((pt) => (
                <option key={pt} value={pt}>
                  {labels.periodType(pt)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <p className="text-[11px] text-gray-500">{t("method_note")}</p>

      {ids.length < MIN_INSTITUTIONS ? (
        <EmptyState title={t("select_title")} description={t("select_hint")} icon="⚖️" />
      ) : result === null || result.status === "loading" ? (
        <TableSkeleton rows={4} cols={5} />
      ) : result.status === "error" ? (
        <ErrorState />
      ) : (
        <section className="space-y-3">
          <h2 className="text-lg font-bold text-white">
            {indicatorLabel(result.data.metric_code)}
            {result.data.period_year !== null ? ` — ${result.data.period_year}` : ""}
            <span className="ml-2 text-[11px] font-normal text-gray-500">
              {labels.scope(result.data.data_scope)} · {labels.periodType(result.data.period_type)}
            </span>
          </h2>
          {(result.data.status === "needs_review" || result.data.status === "unavailable") && (
            <div role="alert" className="p-3 rounded-xl border border-amber-800/60 bg-amber-950/30 text-xs text-amber-200">
              {reason(result.data.reason)}
            </div>
          )}
          <ComparisonTable result={result.data} onProvenance={setProvenance} />
        </section>
      )}

      {/* Sector and UMOA comparisons always reflect the backend answer, including
          "aggregate_not_supported" for ratios / growth (no aggregation method is invented). */}
      <>
          {sector.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-lg font-bold text-white">{t("sector_title")}</h2>
              <p className="text-[11px] text-gray-500">{t("sector_note")}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {sector.map(({ id, result: s }) => (
                  <SectorComparisonCard key={id} result={s} institutionName={byId.get(id)?.name_official} />
                ))}
              </div>
            </section>
          )}

          <section className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-white">{t("country_title")}</h2>
                <p className="text-[11px] text-gray-500">{t("sector_note")}</p>
              </div>
              <label className="text-[11px] text-gray-400 font-medium w-56">
                {t("country_label")}
                <select value={countryCode ?? ""} onChange={(e) => set({ country: e.target.value })} className={selectCls}>
                  <option value="">{MISSING}</option>
                  {UMOA_COUNTRY_CODES.map((c) => (
                    <option key={c} value={c}>
                      {tCountries(c)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {!countryCode ? (
              <p className="text-xs text-gray-500">{t("country_hint")}</p>
            ) : country === null || country.status === "loading" ? (
              <TableSkeleton rows={2} cols={3} />
            ) : country.status === "error" ? (
              <ErrorState />
            ) : (
              <CountryComparisonCard result={country.data} countryName={tCountries(countryCode)} />
            )}
          </section>
      </>

      {provenance && (
        <ProvenancePanel
          dataId={provenance.provenance.length > 1 ? null : provenance.data_id}
          sources={provenance.provenance.length > 1 || !provenance.data_id ? provenance.provenance : null}
          onClose={() => setProvenance(null)}
        />
      )}
    </div>
  );
}
