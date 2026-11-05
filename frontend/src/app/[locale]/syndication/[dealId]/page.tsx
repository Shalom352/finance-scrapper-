"use client";

import React, { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { SyndicationContact, SyndicationDealDetail, SyndicationEvent } from "@/types";
import {
  ApiError,
  addSyndicationEvent,
  createSyndicationContact,
  deleteSyndicationContact,
  getSyndicationDeal,
  updateSyndicationDeal,
} from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";

interface PageProps {
  params: Promise<{ dealId: string; locale: string }>;
}

const STAGES = ["approached", "interested", "declined", "term_sheet", "committed", "disbursed", "withdrawn"] as const;
const STATUSES = ["prospect", "active", "on_hold", "closed_won", "closed_lost"] as const;
const LENDER_TYPES = ["dfi", "bank", "guarantor", "investor", "other"] as const;
const fieldCls = "w-full min-h-10 px-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800";
const btn = "min-h-10 px-4 rounded-xl text-sm font-semibold disabled:opacity-40";

function Section({ title, children, testId }: { title: string; children: React.ReactNode; testId: string }) {
  return (
    <section className="p-4 rounded-2xl border border-gray-200 bg-white space-y-3" data-testid={testId}>
      <h2 className="text-sm font-bold text-gray-900">{title}</h2>
      {children}
    </section>
  );
}

export default function SyndicationDealPage({ params }: PageProps) {
  const { dealId } = use(params);
  const t = useTranslations("syndication");
  const tNav = useTranslations("nav");
  const [deal, setDeal] = useState<SyndicationDealDetail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "not_found" | "error">("loading");
  const load = useCallback(() => {
    getSyndicationDeal(dealId)
      .then((d) => { setDeal(d); setState("ready"); })
      .catch((err) => setState(err instanceof ApiError && err.status === 404 ? "not_found" : "error"));
  }, [dealId]);
  useEffect(load, [load]);

  if (state === "loading") return <TableSkeleton rows={6} cols={4} />;
  if (state === "not_found") return <EmptyState title={t("detail.not_found")} icon="🔎" backHref="/syndication" backText={tNav("syndication")} />;
  if (state === "error" || !deal) return <ErrorState onRetry={load} />;
  return <DealView deal={deal} onChange={load} />;
}

function DealView({ deal, onChange }: { deal: SyndicationDealDetail; onChange: () => void }) {
  const t = useTranslations("syndication");
  const none = <span className="text-gray-400">{t("not_set")}</span>;
  const [openHistory, setOpenHistory] = useState<string | null>(null);
  const [edit, setEdit] = useState({ status: deal.status, notes: deal.notes ?? "" });
  const [event, setEvent] = useState<Partial<SyndicationEvent>>({ stage: "approached" });
  const [contact, setContact] = useState<Partial<SyndicationContact>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const run = async (action: () => Promise<unknown>, after?: () => void) => {
    setMessage(null);
    try {
      await action();
      after?.();
      onChange();
      setMessage(t("detail.saved"));
    } catch {
      setMessage(t("detail.save_error"));
    }
  };

  return (
    <div className="space-y-4 pb-12" data-testid="syndication-deal">
      <Link href="/syndication" className="text-xs text-emerald-700 hover:underline">← {t("detail.back")}</Link>
      <div>
        <h1 className="text-xl md:text-2xl font-black text-gray-900 break-words" data-testid="syndication-deal-title">{deal.title}</h1>
        <p className="text-xs text-gray-500 mt-1">
          {deal.country_code_raw ?? deal.country_code ?? t("not_set")} · {t(`statuses.${deal.status}`)}
          {deal.stage_raw && <> · {deal.stage_raw}</>} · {t(`origins.${deal.origin}`)}
          {deal.last_updated_from_file && <> · {t("detail.file_date", { date: deal.last_updated_from_file })}</>}
          {deal.manually_edited_at && <> · {t("detail.edited")}</>}
        </p>
      </div>
      {message && <p className="text-xs text-gray-700" role="status">{message}</p>}

      <Section title={t("detail.counterparties")} testId="syndication-counterparties">
        {deal.counterparty_states.length === 0 ? (
          <p className="text-xs text-gray-500">{t("detail.no_counterparty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-gray-500 border-b border-gray-100">
                {["institution", "type", "stage", "appetite", "ticket", "rate", "arrangement_fee", "commitment_fee",
                  "maturity", "dossier", "nda", "next_steps"].map((c) =>
                  <th key={c} className="py-2 pr-3 whitespace-nowrap">{t(`columns.${c}`)}</th>)}
              </tr></thead>
              <tbody>
                {deal.counterparty_states.map((s) => (
                  <React.Fragment key={s.id}>
                    <tr className="border-b border-gray-50 align-top" data-testid="syndication-counterparty">
                      <td className="py-2 pr-3 font-semibold">
                        {s.counterparty_name}
                        {!s.institution_id && !s.entity_id && <div className="font-normal text-amber-700">{t("not_linked")}</div>}
                        {s.history.length > 1 && (
                          <button type="button" className="block font-normal text-emerald-700 hover:underline"
                            onClick={() => setOpenHistory(openHistory === s.id ? null : s.id)}>
                            {t("detail.history", { count: s.history.length })}
                          </button>
                        )}
                      </td>
                      <td className="py-2 pr-3">{s.lender_type ? t(`lender_types.${s.lender_type}`) : none}</td>
                      <td className="py-2 pr-3">{t(`stages.${s.stage}`)}</td>
                      <td className="py-2 pr-3">{s.appetite === null ? none : s.appetite ? t("yes") : t("no")}</td>
                      <td className="py-2 pr-3 whitespace-pre-line">{s.amount_text ?? none}</td>
                      <td className="py-2 pr-3 whitespace-pre-line">{s.rate_text ?? none}</td>
                      <td className="py-2 pr-3">{s.arrangement_fee_text ?? none}</td>
                      <td className="py-2 pr-3">{s.commitment_fee_text ?? none}</td>
                      <td className="py-2 pr-3 whitespace-pre-line">{s.maturity_text ?? none}</td>
                      <td className="py-2 pr-3">{s.dossier_status_raw ?? none}</td>
                      <td className="py-2 pr-3">{[s.nda_sent_on, s.nda_received_on].filter(Boolean).join(" → ") || none}</td>
                      <td className="py-2 pr-3 whitespace-pre-line">{s.next_steps ?? none}</td>
                    </tr>
                    {openHistory === s.id && s.history.slice().reverse().map((h) => (
                      <tr key={h.id} className="bg-gray-50 text-gray-600" data-testid="syndication-history-row">
                        <td className="py-1 pr-3 pl-4">{t(`origins.${h.origin}`)} · {h.contact_date ?? h.created_at.slice(0, 10)} · {h.recorded_by}</td>
                        <td className="py-1 pr-3" />
                        <td className="py-1 pr-3">{t(`stages.${h.stage}`)}</td>
                        <td className="py-1 pr-3" colSpan={9}>{[h.amount_text, h.rate_text, h.dossier_status_raw, h.notes].filter(Boolean).join(" · ")}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <form className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 pt-2 border-t border-gray-100"
          onSubmit={(e) => { e.preventDefault(); if (event.counterparty_name) run(() => addSyndicationEvent(deal.id, event)); }}
          data-testid="syndication-add-event">
          <input className={fieldCls} placeholder={t("columns.institution")} value={event.counterparty_name ?? ""}
            onChange={(e) => setEvent({ ...event, counterparty_name: e.target.value })} />
          <select className={fieldCls} value={event.stage} onChange={(e) => setEvent({ ...event, stage: e.target.value })}>
            {STAGES.map((s) => <option key={s} value={s}>{t(`stages.${s}`)}</option>)}
          </select>
          <select className={fieldCls} value={event.lender_type ?? ""} onChange={(e) => setEvent({ ...event, lender_type: e.target.value || null })}>
            <option value="">{t("columns.type")}</option>
            {LENDER_TYPES.map((s) => <option key={s} value={s}>{t(`lender_types.${s}`)}</option>)}
          </select>
          <input className={fieldCls} placeholder={t("columns.ticket")} value={event.amount_text ?? ""}
            onChange={(e) => setEvent({ ...event, amount_text: e.target.value || null })} />
          <input className={fieldCls} placeholder={t("columns.rate")} value={event.rate_text ?? ""}
            onChange={(e) => setEvent({ ...event, rate_text: e.target.value || null })} />
          <input className={fieldCls} placeholder={t("columns.maturity")} value={event.maturity_text ?? ""}
            onChange={(e) => setEvent({ ...event, maturity_text: e.target.value || null })} />
          <input className={fieldCls} placeholder={t("columns.next_steps")} value={event.next_steps ?? ""}
            onChange={(e) => setEvent({ ...event, next_steps: e.target.value || null })} />
          <button type="submit" disabled={!event.counterparty_name} className={`${btn} bg-emerald-600 text-white`}>
            {t("detail.add_event")}
          </button>
        </form>
      </Section>

      <Section title={t("detail.edit")} testId="syndication-edit">
        <form className="grid grid-cols-1 sm:grid-cols-3 gap-2"
          onSubmit={(e) => { e.preventDefault(); run(() => updateSyndicationDeal(deal.id, { status: edit.status, notes: edit.notes || null })); }}>
          <select className={fieldCls} value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })}
            data-testid="syndication-status">
            {STATUSES.map((s) => <option key={s} value={s}>{t(`statuses.${s}`)}</option>)}
          </select>
          <input className={fieldCls} placeholder={t("detail.notes")} value={edit.notes}
            onChange={(e) => setEdit({ ...edit, notes: e.target.value })} />
          <button type="submit" className={`${btn} border border-gray-300 bg-white text-gray-700`}>{t("detail.save")}</button>
        </form>
        <p className="text-[11px] text-gray-500">{t("detail.edit_hint")}</p>
      </Section>

      <Section title={t("detail.contacts")} testId="syndication-deal-contacts">
        {deal.contacts.length === 0 ? <p className="text-xs text-gray-500">{t("detail.no_contact")}</p> : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            {deal.contacts.map((c) => (
              <li key={c.id} className="p-3 rounded-xl border border-gray-200 bg-gray-50">
                <div className="font-semibold text-gray-900">{c.full_name ?? c.email}</div>
                <div className="text-gray-600">{c.job_title ?? ""} · {c.institution_name}</div>
                {c.email && <a href={`mailto:${c.email}`} className="text-emerald-700 hover:underline">{c.email}</a>}
                {c.phone && <div className="text-gray-600 whitespace-pre-line">{c.phone}</div>}
                {c.dataroom_access && <div className="text-gray-500">{t("columns.dataroom")}</div>}
                {confirmRemove === c.id ? (
                  <span className="flex flex-wrap gap-2 mt-1" data-testid="contact-remove-confirm">
                    <button type="button" className="text-rose-700 font-semibold hover:underline"
                      onClick={() => run(() => deleteSyndicationContact(c.id), () => setConfirmRemove(null))}>
                      {t("detail.remove_confirm")}
                    </button>
                    <button type="button" className="text-gray-600 hover:underline" onClick={() => setConfirmRemove(null)}>
                      {t("detail.remove_cancel")}
                    </button>
                  </span>
                ) : (
                  <button type="button" className="text-rose-700 hover:underline mt-1" onClick={() => setConfirmRemove(c.id)}>
                    {t("detail.remove")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        <form className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 pt-2 border-t border-gray-100"
          onSubmit={(e) => { e.preventDefault(); run(() => createSyndicationContact({ ...contact, mandate_id: deal.id }), () => setContact({})); }}>
          {(["institution_name", "full_name", "job_title", "email", "phone"] as const).map((f) => (
            <input key={f} className={fieldCls} placeholder={t(`contact_fields.${f}`)} aria-label={t(`contact_fields.${f}`)} value={(contact[f] as string) ?? ""}
              onChange={(e) => setContact({ ...contact, [f]: e.target.value || null })} />
          ))}
          <button type="submit" disabled={!contact.institution_name || !(contact.full_name || contact.email)}
            className={`${btn} bg-emerald-600 text-white`}>{t("detail.add_contact")}</button>
        </form>
      </Section>
    </div>
  );
}
