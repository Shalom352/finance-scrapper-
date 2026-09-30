"use client";

import React, { Suspense, use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { ReviewDetail, ReviewEvent } from "@/types";
import { ApiError, getReviewDetail, getReviewHistory } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { displayCurrency, MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { useQueryParams } from "@/lib/useQueryParams";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { CompetingObservations } from "@/components/data-quality/CompetingObservations";
import { ReviewHistory } from "@/components/data-quality/ReviewHistory";
import { ReviewActions } from "@/components/data-quality/ReviewActions";

interface PageProps {
  params: Promise<{ dataId: string; locale: string }>;
}

export default function ReviewDetailPage({ params }: PageProps) {
  const { dataId } = use(params);
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={4} />}>
      <ReviewDetailContent dataId={dataId} />
    </Suspense>
  );
}

type Load = { status: "loading" } | { status: "not_found" } | { status: "error" } | { status: "ready"; detail: ReviewDetail; history: ReviewEvent[] };

function ReviewDetailContent({ dataId }: { dataId: string }) {
  const t = useTranslations("data_quality");
  const td = useTranslations("data_quality.detail");
  const tc = useTranslations("data_quality.competing");
  const tq = useTranslations("data_explorer.qualification");
  const labels = useLabels();
  const fmt = useFormatters();
  const { searchParams } = useQueryParams();
  const qs = searchParams.toString();
  const suffix = qs ? `?${qs}` : "";

  const [state, setState] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);
  const [provenance, setProvenance] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getReviewDetail(dataId), getReviewHistory(dataId)])
      .then(([detail, history]) => !cancelled && setState({ status: "ready", detail, history }))
      .catch((err) => {
        if (cancelled) return;
        setState({ status: err instanceof ApiError && err.status === 404 ? "not_found" : "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [dataId, reload]);

  const back = (
    <Link href={`/data-quality${suffix}`} className="text-xs text-emerald-300 hover:underline" data-testid="dq-back">
      ← {t("back")}
    </Link>
  );

  if (state.status === "loading") return <TableSkeleton rows={6} cols={4} />;
  if (state.status === "not_found")
    return (
      <div className="space-y-4">
        {back}
        <EmptyState title={td("not_found")} icon="🔎" />
      </div>
    );
  if (state.status === "error")
    return (
      <div className="space-y-4">
        {back}
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      </div>
    );

  const { detail, history } = state;
  const o = detail.observation;
  const num = (v: number | null) => (v === null ? td("missing") : fmt.number(v, Number.isInteger(v) ? 0 : 2));
  const facts: [string, React.ReactNode][] = [
    [td("id"), <span key="id" className="font-mono">{o.id}</span>],
    [td("institution"), (
      <Link key="inst" href={`/institutions/${o.institution_id}`} className="hover:text-emerald-300 hover:underline">
        {o.institution?.name_official ?? MISSING}
      </Link>
    )],
    [td("country"), detail.country_code ? labels.country(null, detail.country_code) : MISSING],
    [td("indicator"), labels.metric(o.metric_code)],
    [td("original_value"), [o.value_original, o.unit_original, o.currency_original].filter(Boolean).join(" ") || MISSING],
    [td("normalized_value"), num(o.value_normalized)],
    [td("unit"), o.unit_normalized || MISSING],
    [td("currency"), displayCurrency(o.currency_normalized) || MISSING],
    [td("year"), o.period_year],
    [td("period_type"), labels.periodType(o.period_type)],
    [td("scope"), labels.scope(o.scope)],
    [td("status"), <StatusBadge key="st" status={o.status} size="sm" />],
    [td("qualification"), detail.qualification ? tq(detail.qualification) : MISSING],
    [td("extraction_method"), o.extraction_method],
    [td("document"), o.document?.title ?? MISSING],
    [td("page"), o.page_number ?? MISSING],
    [td("source"), o.source?.name ?? MISSING],
    [td("created_at"), fmt.date(o.created_at)],
    [td("updated_at"), fmt.date(o.updated_at)],
    [td("verified_by"), o.verified_by ?? MISSING],
  ];
  const hrefFor = (id: string) => `/data-quality/${id}${suffix}`;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {back}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-black text-white tracking-tight">
          {td("title")} — {labels.metric(o.metric_code)} {o.period_year}
        </h1>
        <button type="button" onClick={() => setProvenance(true)} data-testid="dq-provenance"
          className="px-3 py-2 rounded-xl border border-gray-700 bg-gray-900 text-xs font-semibold text-gray-200 hover:border-emerald-500">
          {td("provenance")}
        </button>
      </div>

      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs" data-testid="dq-facts">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-gray-500">{label}</dt>
            <dd className="text-gray-100 font-medium break-all">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="space-y-2">
        <h2 className="text-sm font-bold text-white">{tc("title")}</h2>
        {detail.qualification === "conflict" && (
          <p role="note" className="p-3 rounded-xl border border-amber-800/60 bg-amber-950/30 text-xs text-amber-200" data-testid="dq-conflict-guide">
            {tc("conflict_guide")}
          </p>
        )}
        {detail.competing.length > 1 ? (
          <CompetingObservations currentId={o.id} rows={detail.competing} comparable hrefFor={hrefFor} />
        ) : (
          <p className="text-xs text-gray-500">{tc("none")}</p>
        )}
      </section>

      {detail.not_comparable.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-bold text-white">{tc("not_comparable_title")}</h2>
          <CompetingObservations currentId={o.id} rows={detail.not_comparable} comparable={false} hrefFor={hrefFor} />
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-bold text-white">{t("history.title")}</h2>
        <ReviewHistory events={history} />
      </section>

      <ReviewActions
        key={`${o.status}-${o.updated_at}`}
        dataId={o.id}
        allowed={detail.allowed_actions}
        expectedStatus={o.status}
        expectedUpdatedAt={o.updated_at}
        onDone={() => setReload((n) => n + 1)}
      />
      <p className="text-[11px] text-gray-500">{t("auth_note")}</p>

      {provenance && <ProvenancePanel dataId={o.id} onClose={() => setProvenance(false)} />}
    </div>
  );
}
