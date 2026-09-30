"use client";

import React, { Suspense, use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { DealDetail, ReviewEvent } from "@/types";
import { getDeal, getDealHistory } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { useQueryParams } from "@/lib/useQueryParams";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { DealDetailView } from "@/components/deals/DealDetailView";

interface PageProps {
  params: Promise<{ dealId: string; locale: string }>;
}

export default function DealPage({ params }: PageProps) {
  const { dealId } = use(params);
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={4} />}>
      <DealContent dealId={dealId} />
    </Suspense>
  );
}

type Load = { status: "loading" } | { status: "not_found" } | { status: "error" } | { status: "ready"; deal: DealDetail; history: ReviewEvent[] };

function DealContent({ dealId }: { dealId: string }) {
  const t = useTranslations("deals.detail");
  const { searchParams } = useQueryParams();
  const qs = searchParams.toString();
  const [state, setState] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for a new deal
    setState({ status: "loading" });
    Promise.all([getDeal(dealId), getDealHistory(dealId)])
      .then(([deal, history]) => !cancelled && setState({ status: "ready", deal, history }))
      .catch((err: { status?: number }) => !cancelled && setState({ status: err?.status === 404 ? "not_found" : "error" }));
    return () => {
      cancelled = true;
    };
  }, [dealId, reload]);

  const back = (
    <Link href={`/deals${qs ? `?${qs}` : ""}`} className="text-xs text-emerald-300 hover:underline" data-testid="deal-back">
      ← {t("back")}
    </Link>
  );
  if (state.status === "loading") return <TableSkeleton rows={6} cols={4} />;
  if (state.status === "not_found")
    return (
      <div className="space-y-4">
        {back}
        <EmptyState title={t("not_found")} icon="🔎" />
      </div>
    );
  if (state.status === "error")
    return (
      <div className="space-y-4">
        {back}
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      </div>
    );

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {back}
      <h1 className="text-2xl font-black text-white tracking-tight" data-testid="deal-title">{state.deal.title}</h1>
      <DealDetailView deal={state.deal} history={state.history} reviewHref={`/data-quality/deals/${state.deal.id}`} />
    </div>
  );
}
