"use client";

import React from "react";
import { useLocale, useTranslations } from "next-intl";
import type { DealDetail, DealSource, ReviewEvent } from "@/types";
import { Link } from "@/i18n/navigation";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { formatDay } from "@/lib/deals";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ReviewHistory } from "@/components/data-quality/ReviewHistory";
import { useDealLabels } from "@/components/deals/DealLabels";
import { useDealAmount } from "@/components/deals/DealAmount";

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3" data-testid={testId}>
      <h2 className="text-sm font-bold text-white">{title}</h2>
      {children}
    </section>
  );
}

/** Pages of the sources attesting one field (field-level provenance). Nothing shown = no source claims it. */
function FieldSources({ ids, byId }: { ids: string[] | undefined; byId: Map<string, DealSource> }) {
  const t = useTranslations("deals.detail");
  if (!ids || ids.length === 0) return null;
  return (
    <span className="ml-1 text-[10px] text-gray-500">
      {ids.map((id) => {
        const s = byId.get(id);
        return s ? (
          <a key={id} href={`#deal-source-${id}`} className="mr-1 hover:text-emerald-300"
            title={`${s.source_name ?? ""} — ${s.document_title ?? ""}`}>
            [{t("page", { page: s.page_number })}]
          </a>
        ) : null;
      })}
    </span>
  );
}

function SourceCard({ s, fieldLabel }: { s: DealSource; fieldLabel: (f: string) => string }) {
  const t = useTranslations("deals.detail");
  return (
    <li id={`deal-source-${s.id}`} className="p-3 rounded-xl border border-gray-800 bg-gray-950/40 text-xs space-y-1" data-testid="deal-source">
      <div className="text-gray-200 font-semibold">
        {s.document_title ?? MISSING} · {t("page", { page: s.page_number })}
      </div>
      <div className="text-gray-400">{s.source_name ?? MISSING}</div>
      {s.excerpt && <blockquote className="text-gray-300 italic border-l-2 border-gray-700 pl-2">{s.excerpt}</blockquote>}
      {s.fields.length > 0 && (
        <div className="text-gray-500">{t("attests")} {s.fields.map(fieldLabel).join(", ")}</div>
      )}
      {s.document_url && (
        <a href={s.document_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
          {t("open_document")} ↗
        </a>
      )}
    </li>
  );
}

export function DealDetailView({ deal, history, reviewHref }: { deal: DealDetail; history: ReviewEvent[]; reviewHref?: string }) {
  const t = useTranslations("deals.detail");
  const tf = useTranslations("deals.detail.fields");
  const tDup = useTranslations("deals.duplicates");
  const tCountries = useTranslations("country_names");
  const locale = useLocale();
  const fmt = useFormatters();
  const labels = useDealLabels();
  const amount = useDealAmount();
  const byId = new Map(deal.sources.map((s) => [s.id, s]));
  const prov = deal.field_provenance;
  const unavailable = <span className="text-gray-500">{t("unavailable")}</span>;
  const text = (v: string | null) => (v ? v : unavailable);

  const row = (field: string, value: React.ReactNode, hasValue: boolean) => (
    <div key={field}>
      <dt className="text-gray-500">{tf(field)}</dt>
      <dd className="text-gray-100 font-medium break-words" data-testid={`deal-field-${field}`}>
        {hasValue ? value : unavailable}
        {hasValue && <FieldSources ids={prov[field]} byId={byId} />}
      </dd>
    </div>
  );

  const byRole = new Map<string, typeof deal.participants>();
  for (const p of deal.participants) byRole.set(p.role, [...(byRole.get(p.role) ?? []), p]);
  const borrowers = byRole.get("borrower") ?? [];
  const sponsors = byRole.get("sponsor") ?? [];
  const dates = ["announcement_date", "signing_date", "financial_close_date", "closing_date"] as const;

  return (
    <div className="space-y-4">
      {deal.merged_into_deal_id && (
        <p role="note" className="p-3 rounded-xl border border-amber-800/60 bg-amber-950/30 text-xs text-amber-200" data-testid="deal-merged-note">
          {t("merged_into")}{" "}
          <Link href={`/deals/${deal.merged_into_deal_id}`} className="underline">{t("open_primary")}</Link>
        </p>
      )}

      <Section title={t("summary")} testId="deal-summary">
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 text-xs">
          {row("title", deal.title, true)}
          {row("deal_type", labels.type(deal.deal_type), deal.deal_type !== null)}
          {row("country_code", deal.country_code ? (tCountries.has(deal.country_code) ? tCountries(deal.country_code) : deal.country_code) : null, deal.country_code !== null)}
          {row("sector", deal.sector, deal.sector !== null)}
          <div>
            <dt className="text-gray-500">{tf("status")}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <StatusBadge status={deal.status} size="sm" />
              {deal.verified_by && <span className="text-gray-400">{t("verified_by", { actor: deal.verified_by })}</span>}
            </dd>
          </div>
        </dl>
        {reviewHref && (
          <Link href={reviewHref} className="inline-block text-xs text-emerald-300 hover:underline" data-testid="deal-review-link">
            {t("review_link")} →
          </Link>
        )}
      </Section>

      <Section title={t("financial_terms")} testId="deal-terms">
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 text-xs">
          {row("amount", amount(deal.amount, deal.currency, deal.unit), deal.amount !== null)}
          {row("amount_original", deal.amount_original, deal.amount_original !== null)}
          {row("interest_rate", fmt.percent(deal.interest_rate, 2), deal.interest_rate !== null)}
          {row("interest_rate_type", labels.rateType(deal.interest_rate_type), deal.interest_rate_type !== null)}
          {row("benchmark", deal.benchmark, deal.benchmark !== null)}
          {row("spread_bps", deal.spread_bps !== null ? t("bps", { value: fmt.number(deal.spread_bps, Number.isInteger(deal.spread_bps) ? 0 : 2) }) : null, deal.spread_bps !== null)}
          {row("maturity_months", deal.maturity_months !== null ? t("months", { count: deal.maturity_months }) : null, deal.maturity_months !== null)}
          {row("grace_period_months", deal.grace_period_months !== null ? t("months", { count: deal.grace_period_months }) : null, deal.grace_period_months !== null)}
          {row("fees", deal.fees, deal.fees !== null)}
        </dl>
      </Section>

      <Section title={t("participants")} testId="deal-participants">
        {deal.participants.length === 0 ? (
          <p className="text-xs text-gray-500">{t("no_participants")}</p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            {deal.participants.map((p) => {
              const s = byId.get(p.deal_source_id);
              return (
                <li key={p.id} className="p-3 rounded-xl border border-gray-800 bg-gray-950/40" data-testid="deal-participant">
                  <span className="px-1.5 py-0.5 mr-2 rounded bg-gray-800 text-[10px] text-gray-300 uppercase">{labels.role(p.role)}</span>
                  {p.institution_id ? (
                    <Link href={`/institutions/${p.institution_id}`} className="font-semibold text-emerald-300 hover:underline">
                      {p.institution_name ?? p.participant_name}
                    </Link>
                  ) : (
                    <span className="font-semibold text-gray-100">{p.participant_name}</span>
                  )}
                  <span className="block text-gray-500 mt-1">
                    {p.institution_id ? t("institution") : t("not_in_directory")}
                    {p.commitment_amount !== null && <> · {t("commitment")} {amount(p.commitment_amount, p.commitment_currency, null)}</>}
                    {s && <> · <a href={`#deal-source-${s.id}`} className="hover:text-emerald-300">{t("page", { page: s.page_number })}</a></>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title={t("timeline")} testId="deal-timeline">
        <ol className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
          {dates.map((f) => (
            <li key={f} className="p-3 rounded-xl border border-gray-800 bg-gray-950/40">
              <div className="text-gray-500">{tf(f)}</div>
              <div className="text-gray-100 font-medium" data-testid={`deal-field-${f}`}>
                {deal[f] ? formatDay(deal[f], locale) : <span className="text-gray-500">{t("not_published")}</span>}
                {deal[f] && <FieldSources ids={prov[f]} byId={byId} />}
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title={t("project_borrower")} testId="deal-project">
        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-3 text-xs">
          {row("project_name", deal.project_name, deal.project_name !== null)}
          <div>
            <dt className="text-gray-500">{labels.role("borrower")}</dt>
            <dd className="text-gray-100 font-medium">{borrowers.length ? borrowers.map((p) => p.participant_name).join(", ") : unavailable}</dd>
          </div>
          <div>
            <dt className="text-gray-500">{labels.role("sponsor")}</dt>
            <dd className="text-gray-100 font-medium">{sponsors.length ? sponsors.map((p) => p.participant_name).join(", ") : unavailable}</dd>
          </div>
        </dl>
      </Section>

      <Section title={t("guarantees")} testId="deal-guarantees">
        <p className="text-xs text-gray-100" data-testid="deal-field-guarantees">
          {text(deal.guarantees)}
          {deal.guarantees && <FieldSources ids={prov.guarantees} byId={byId} />}
        </p>
      </Section>

      <Section title={t("sources")} testId="deal-sources">
        {deal.sources.length === 0 ? (
          <p className="text-xs text-gray-500">{t("no_sources")}</p>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {deal.sources.map((s) => <SourceCard key={s.id} s={s} fieldLabel={labels.field} />)}
          </ul>
        )}
        {deal.merged_deals.length > 0 && (
          <div className="space-y-2" data-testid="deal-merged">
            <h3 className="text-xs font-semibold text-gray-300">{t("merged_deals")}</h3>
            {deal.merged_deals.map((m) => (
              <div key={m.id} className="space-y-1">
                <Link href={`/deals/${m.id}`} className="text-xs text-emerald-300 hover:underline">{m.title}</Link>
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {m.sources.map((s) => <SourceCard key={s.id} s={s} fieldLabel={labels.field} />)}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title={tDup("title")} testId="deal-duplicates">
        <p className="text-[11px] text-gray-500">{tDup("note")}</p>
        {deal.duplicates.length === 0 ? (
          <p className="text-xs text-gray-500">{tDup("none")}</p>
        ) : (
          <ul className="space-y-2 text-xs">
            {deal.duplicates.map((c) => (
              <li key={c.id} className="p-3 rounded-xl border border-gray-800 bg-gray-950/40" data-testid="deal-duplicate">
                <div className={c.state === "duplicate_candidate" ? "text-amber-300 font-semibold" : "text-gray-200 font-semibold"}>
                  {tDup(`state.${c.state}`, { actor: c.decided_by ?? MISSING })}
                </div>
                <div className="text-gray-400 mt-1">
                  {tDup("other")}{" "}
                  <Link href={`/deals/${c.other_deal_id}`} className="text-emerald-300 hover:underline">
                    {c.other_deal_title ?? c.other_deal_id}
                  </Link>
                </div>
                <div className="text-gray-500 mt-1">
                  {tDup("criteria")} {c.matched_criteria.map(labels.criterion).join(" · ")}
                </div>
                {c.decision_reason && <p className="mt-1 text-gray-300 italic">{c.decision_reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={t("review_history")} testId="deal-history">
        <ReviewHistory events={history} />
      </Section>
    </div>
  );
}
