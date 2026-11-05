"use client";

import React, { Suspense, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import type { SyndicationContact, SyndicationDeal, SyndicationLender, SyndicationTerm } from "@/types";
import {
  listSyndicationContacts,
  listSyndicationDeals,
  listSyndicationLenders,
  listSyndicationTerms,
} from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { useQueryParams } from "@/lib/useQueryParams";
import { SyndicationImportPanel } from "@/components/syndication/SyndicationImportPanel";

type Tab = "deals" | "lenders" | "terms" | "contacts";
const TABS: Tab[] = ["deals", "lenders", "terms", "contacts"];
const th = "py-2 px-3 text-left text-xs font-semibold text-gray-500 whitespace-nowrap";
const td = "py-2 px-3 text-xs text-gray-800 align-top";

/** Internal syndication pipeline (TOMASTEED). Values as written in the tracker; nothing estimated. */
export default function SyndicationPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={5} />}>
      <SyndicationContent />
    </Suspense>
  );
}

function SyndicationContent() {
  const t = useTranslations("syndication");
  // Tab and text filter live in the URL: a view can be shared and survives a reload.
  const { get, set } = useQueryParams();
  const tabParam = get("tab") as Tab;
  const tab: Tab = TABS.includes(tabParam) ? tabParam : "deals";
  const setTab = (x: Tab) => set({ tab: x === "deals" ? null : x });
  const query = get("q");
  const setQuery = (value: string) => set({ q: value || null });
  const [deals, setDeals] = useState<SyndicationDeal[] | null>(null);
  const [lenders, setLenders] = useState<SyndicationLender[] | null>(null);
  const [terms, setTerms] = useState<SyndicationTerm[] | null>(null);
  const [contacts, setContacts] = useState<SyndicationContact[] | null>(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for a new tab
    setError(false);
    const load: Record<Tab, () => Promise<void>> = {
      deals: () => listSyndicationDeals().then((x) => { if (!cancelled) setDeals(x); }),
      lenders: () => listSyndicationLenders().then((x) => { if (!cancelled) setLenders(x); }),
      terms: () => listSyndicationTerms().then((x) => { if (!cancelled) setTerms(x); }),
      contacts: () => listSyndicationContacts().then((x) => { if (!cancelled) setContacts(x); }),
    };
    load[tab]().catch(() => !cancelled && setError(true));
    return () => { cancelled = true; };
  }, [tab, reload]);

  const q = query.trim().toLowerCase();
  const match = (...values: (string | null | undefined)[]) => !q || values.some((v) => v?.toLowerCase().includes(q));
  const none = <span className="text-gray-400">{t("not_set")}</span>;
  const rows = useMemo(() => ({
    deals: (deals ?? []).filter((d) => match(d.title, d.client_name, d.country_code_raw)),
    lenders: (lenders ?? []).filter((l) => match(l.name, ...l.countries)),
    terms: (terms ?? []).filter((x) => match(x.institution, x.deal, x.country)),
    contacts: (contacts ?? []).filter((c) => match(c.institution_name, c.full_name, c.email, c.job_title)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [deals, lenders, terms, contacts, q]);
  const loaded = { deals, lenders, terms, contacts }[tab];

  return (
    <div className="space-y-5 animate-fade-in pb-12" data-testid="syndication-page">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-gray-900 tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-500 mt-1 max-w-3xl">{t("subtitle")}</p>
      </div>

      <details className="rounded-2xl border border-gray-200/90 bg-white shadow-xs">
        <summary className="px-4 sm:px-5 py-3 cursor-pointer text-sm font-semibold text-gray-900">{t("import_title")}</summary>
        <div className="px-1 pb-1">
          <SyndicationImportPanel />
        </div>
      </details>

      <div data-guide="syndication" className="flex flex-wrap items-center gap-2" role="tablist">
        {TABS.map((x) => (
          <button key={x} type="button" role="tab" aria-selected={tab === x} onClick={() => setTab(x)}
            className={`min-h-10 px-4 rounded-xl text-sm font-medium border ${tab === x
              ? "bg-emerald-600 border-emerald-600 text-white" : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"}`}
            data-testid={`syndication-tab-${x}`}>
            {t(`tabs.${x}`)}
          </button>
        ))}
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("search")}
          className="ml-auto min-h-10 px-3 rounded-xl border border-gray-200 text-sm w-full sm:w-64" data-testid="syndication-search" />
      </div>

      <section className="rounded-2xl border border-gray-200/90 bg-white shadow-xs overflow-hidden">
        {error ? (
          <div className="p-4"><ErrorState onRetry={() => setReload((n) => n + 1)} /></div>
        ) : loaded === null ? (
          <TableSkeleton rows={6} cols={6} />
        ) : rows[tab].length === 0 ? (
          <EmptyState title={t("empty")} description={t("empty_hint")} />
        ) : (
          <div className="overflow-x-auto">
            {tab === "deals" && (
              <table className="w-full" data-testid="syndication-deals">
                <thead><tr className="border-b border-gray-100">
                  {["deal", "country", "status", "approached", "interested", "committed", "declined", "updated"].map((c) =>
                    <th key={c} className={th}>{t(`columns.${c}`)}</th>)}
                </tr></thead>
                <tbody>
                  {rows.deals.map((d) => (
                    <tr key={d.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className={td}>
                        <Link href={`/syndication/${d.id}`} className="font-semibold text-emerald-700 hover:underline">{d.title}</Link>
                        {d.stage_raw && <div className="text-gray-500">{d.stage_raw}</div>}
                      </td>
                      <td className={td}>{d.country_code_raw ?? d.country_code ?? none}</td>
                      <td className={td}>{t(`statuses.${d.status}`)}</td>
                      {(["approached", "interested", "committed", "declined"] as const).map((k) =>
                        <td key={k} className={`${td} text-center`}>{d.counts[k] || "·"}</td>)}
                      <td className={td}>{d.last_updated_from_file ?? none}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === "lenders" && (
              <table className="w-full" data-testid="syndication-lenders">
                <thead><tr className="border-b border-gray-100">
                  {["institution", "type", "countries", "deals", "tickets", "maturities"].map((c) =>
                    <th key={c} className={th}>{t(`columns.${c}`)}</th>)}
                </tr></thead>
                <tbody>
                  {rows.lenders.map((l) => (
                    <tr key={l.name} className="border-b border-gray-50">
                      <td className={`${td} font-semibold`}>
                        {l.name}
                        {!l.institution_id && !l.entity_id && <div className="text-amber-700 font-normal">{t("not_linked")}</div>}
                      </td>
                      <td className={td}>{l.lender_types.map((x) => t(`lender_types.${x}`)).join(", ") || none}</td>
                      <td className={td}>{l.countries.join(", ") || none}</td>
                      <td className={td}>
                        {l.deals.map((d) => (
                          <div key={d.id}><Link href={`/syndication/${d.id}`} className="text-emerald-700 hover:underline">{d.title}</Link>
                            {" "}<span className="text-gray-500">({t(`stages.${d.stage}`)})</span></div>
                        ))}
                      </td>
                      <td className={td}>{l.tickets.join(" · ") || none}</td>
                      <td className={td}>{l.maturities.join(" · ") || none}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === "terms" && (
              <table className="w-full" data-testid="syndication-terms">
                <thead><tr className="border-b border-gray-100">
                  {["institution", "deal", "country", "ticket", "rate", "arrangement_fee", "commitment_fee", "maturity"].map((c) =>
                    <th key={c} className={th}>{t(`columns.${c}`)}</th>)}
                </tr></thead>
                <tbody>
                  {rows.terms.map((x, i) => (
                    <tr key={`${x.deal_id}-${x.institution}-${i}`} className="border-b border-gray-50">
                      <td className={`${td} font-semibold`}>{x.institution}</td>
                      <td className={td}><Link href={`/syndication/${x.deal_id}`} className="text-emerald-700 hover:underline">{x.deal}</Link></td>
                      <td className={td}>{x.country ?? none}</td>
                      <td className={`${td} whitespace-pre-line`}>{x.amount_text ?? none}</td>
                      <td className={`${td} whitespace-pre-line`}>{x.rate_text ?? none}</td>
                      <td className={td}>{x.arrangement_fee_text ?? none}</td>
                      <td className={td}>{x.commitment_fee_text ?? none}</td>
                      <td className={`${td} whitespace-pre-line`}>{x.maturity_text ?? none}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === "contacts" && (
              <table className="w-full" data-testid="syndication-contacts">
                <thead><tr className="border-b border-gray-100">
                  {["institution", "name", "function", "email", "phone", "dataroom"].map((c) =>
                    <th key={c} className={th}>{t(`columns.${c}`)}</th>)}
                </tr></thead>
                <tbody>
                  {rows.contacts.map((c) => (
                    <tr key={c.id} className="border-b border-gray-50">
                      <td className={`${td} font-semibold`}>{c.institution_name}</td>
                      <td className={td}>{c.full_name ?? none}</td>
                      <td className={td}>{c.job_title ?? none}</td>
                      <td className={td}>{c.email ? <a href={`mailto:${c.email}`} className="text-emerald-700 hover:underline">{c.email}</a> : none}</td>
                      <td className={`${td} whitespace-pre-line`}>{c.phone ?? none}</td>
                      <td className={td}>{c.dataroom_access ? t("yes") : "·"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
      <p className="text-[11px] text-gray-500">{t("confidential")}</p>
    </div>
  );
}
