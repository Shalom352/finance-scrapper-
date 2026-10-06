"use client";

import React, { Suspense, use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { DealDetail, ReviewEvent } from "@/types";
import { getDeal, getDealHistory, postDealReviewAction } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { ReviewActions } from "@/components/data-quality/ReviewActions";
import { AutoValidationPanel } from "@/components/data-quality/AutoValidationPanel";
import { DealDetailView } from "@/components/deals/DealDetailView";
import { DuplicateDecisionForm } from "@/components/deals/DuplicateDecisionForm";

interface PageProps {
  params: Promise<{ dealId: string; locale: string }>;
}

export default function DealReviewPage({ params }: PageProps) {
  const { dealId } = use(params);
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={4} />}>
      <DealReviewContent dealId={dealId} />
    </Suspense>
  );
}

type Load = { status: "loading" } | { status: "not_found" } | { status: "error" } | { status: "ready"; deal: DealDetail; history: ReviewEvent[] };

/** Same Review Center, same guarantees as observations: backend-decided transitions, 404 / 409 / 422, audit. */
function DealReviewContent({ dealId }: { dealId: string }) {
  const t = useTranslations("data_quality.deal_review");
  const tq = useTranslations("data_quality");
  const tDup = useTranslations("deals.duplicates");
  const tDetail = useTranslations("deals.detail");
  const [state, setState] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);
  const [done, setDone] = useState<"action" | "duplicate" | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getDeal(dealId), getDealHistory(dealId)])
      .then(([deal, history]) => !cancelled && setState({ status: "ready", deal, history }))
      .catch((err: { status?: number }) => !cancelled && setState({ status: err?.status === 404 ? "not_found" : "error" }));
    return () => {
      cancelled = true;
    };
  }, [dealId, reload]);

  const back = (
    <Link href="/data-quality?tab=deals" className="text-xs text-emerald-300 hover:underline" data-testid="deal-review-back">
      ← {t("back")}
    </Link>
  );
  if (state.status === "loading") return <TableSkeleton rows={6} cols={4} />;
  if (state.status === "not_found")
    return (
      <div className="space-y-4">
        {back}
        <EmptyState title={tDetail("not_found")} icon="🔎" />
      </div>
    );
  if (state.status === "error")
    return (
      <div className="space-y-4">
        {back}
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      </div>
    );

  const { deal, history } = state;
  const open = deal.duplicates.filter((c) => c.state === "duplicate_candidate");
  const refresh = (kind: "action" | "duplicate" | null) => {
    setDone(kind);
    setReload((n) => n + 1);
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {back}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-black text-white tracking-tight">
          {t("title")} — {deal.title}
        </h1>
        <Link href={`/deals/${deal.id}`} className="text-xs text-emerald-300 hover:underline">{t("open_detail")} →</Link>
      </div>

      {open.length > 0 && (
        <section className="p-4 rounded-2xl border border-amber-800/60 bg-amber-950/20 space-y-3" data-testid="deal-open-duplicates">
          <h2 className="text-sm font-bold text-amber-200">{tq("deals_queue.duplicates_title")}</h2>
          <p className="text-[11px] text-amber-200/80">{tDup("note")}</p>
          {open.map((c) => (
            <div key={c.id} className="text-xs text-gray-200">
              <Link href={`/deals/${c.other_deal_id}`} className="font-semibold text-emerald-300 hover:underline">
                {c.other_deal_title ?? c.other_deal_id}
              </Link>
              <DuplicateDecisionForm candidate={c} dealId={deal.id} dealTitle={deal.title} onDone={() => refresh("duplicate")} />
            </div>
          ))}
        </section>
      )}
      {done === "duplicate" && <p className="text-xs text-emerald-300" data-testid="dup-done">{tDup("decide.done")}</p>}

      <AutoValidationPanel
        kind="deal"
        id={deal.id}
        status={deal.status}
        method={deal.validation_method}
        report={deal.auto_validation}
        blocked={deal.auto_validation_blocked}
        onDone={() => refresh(null)}
      />

      <ReviewActions
        key={`${deal.status}-${deal.updated_at}`}
        dataId={deal.id}
        allowed={deal.allowed_actions}
        expectedStatus={deal.status}
        expectedUpdatedAt={deal.updated_at}
        submitAction={(action, decision) => postDealReviewAction(deal.id, action, decision)}
        done={done === "action"}
        onDone={() => refresh("action")}
        onReload={() => refresh(null)}
      />
      <p className="text-[11px] text-gray-500">{tq("auth_note")}</p>

      <DealDetailView deal={deal} history={history} />
    </div>
  );
}
