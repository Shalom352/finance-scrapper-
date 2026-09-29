"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Document } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useLabels } from "@/lib/useLabels";
import { StateBadge } from "@/components/common/StatusBadge";

interface DocumentsTableProps {
  documents: Document[];
  emptyText: string;
  /** Show a link to the owning institution (list responses carry only its id). */
  showInstitution?: boolean;
}

export function DocumentsTable({ documents, emptyText, showInstitution = false }: DocumentsTableProps) {
  const t = useTranslations("documents");
  const tDl = useTranslations("document_download");
  const tEx = useTranslations("document_extraction");
  const labels = useLabels();

  if (documents.length === 0) {
    return <div className="p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-800">{emptyText}</div>;
  }

  const tone = (s: string, ok: string) => (s === ok ? "ok" : s === "failed" ? "error" : "neutral") as "ok" | "error" | "neutral";

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
            <th className="py-3 px-4">{t("columns.title")}</th>
            {showInstitution && <th className="py-3 px-4">{t("columns.institution")}</th>}
            <th className="py-3 px-4">{t("columns.type")}</th>
            <th className="py-3 px-4">{t("columns.year")}</th>
            <th className="py-3 px-4 text-center">{t("columns.download")}</th>
            <th className="py-3 px-4 text-center">{t("columns.extraction")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {documents.map((doc) => (
            <tr key={doc.id} className="hover:bg-gray-800/30 transition-colors">
              <td className="py-3.5 px-4 font-semibold text-gray-200">
                {doc.url ? (
                  <a href={doc.url} target="_blank" rel="noreferrer" className="hover:text-emerald-400">
                    {doc.title} ↗
                  </a>
                ) : (
                  doc.title
                )}
              </td>
              {showInstitution && (
                <td className="py-3.5 px-4 text-gray-300">
                  {doc.institution_id ? (
                    <Link href={`/institutions/${doc.institution_id}`} className="text-emerald-400/90 hover:text-emerald-400">
                      {t("open_institution")}
                    </Link>
                  ) : (
                    <span className="text-gray-500">{t("regional")}</span>
                  )}
                </td>
              )}
              <td className="py-3.5 px-4 text-gray-400">{labels.documentType(doc.document_type)}</td>
              <td className="py-3.5 px-4 font-mono text-gray-300">{doc.period_year ?? MISSING}</td>
              <td className="py-3.5 px-4 text-center">
                <StateBadge
                  label={tDl.has(doc.download_status) ? tDl(doc.download_status) : doc.download_status}
                  tone={tone(doc.download_status, "downloaded")}
                />
              </td>
              <td className="py-3.5 px-4 text-center">
                <StateBadge
                  label={tEx.has(doc.extraction_status) ? tEx(doc.extraction_status) : doc.extraction_status}
                  tone={tone(doc.extraction_status, "extracted")}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
