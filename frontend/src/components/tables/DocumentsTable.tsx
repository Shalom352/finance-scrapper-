"use client";

import { externalHref } from "@/lib/url";
import React from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Document } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useLabels } from "@/lib/useLabels";
import { StateBadge } from "@/components/common/StatusBadge";
import { SortHeader } from "@/components/common/SortHeader";
import { useSort, type SortDir } from "@/lib/useSort";

type DocSortKey = "title" | "type" | "year" | "download" | "extraction";
const FIRST_DIR: Record<DocSortKey, SortDir> = { title: "asc", type: "asc", year: "desc", download: "asc", extraction: "asc" };

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
  // Rows of the current page, newest period first by default (the API orders by ingestion date).
  const { sorted, sortKey, dir, toggle } = useSort(
    documents,
    {
      title: (d) => d.title,
      type: (d) => labels.documentType(d.document_type),
      year: (d) => d.period_year ?? null,
      download: (d) => d.download_status,
      extraction: (d) => d.extraction_status,
    },
    { key: "year", dir: "desc" },
  );
  const head = (key: DocSortKey, cls = "") => (
    <SortHeader label={t(`columns.${key}`)} active={sortKey === key} dir={dir} onClick={() => toggle(key, FIRST_DIR[key])}
      className={`py-3 px-4 ${cls}`} testId={`doc-sort-${key}`} />
  );

  if (documents.length === 0) {
    return <div className="p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-200">{emptyText}</div>;
  }

  const tone = (s: string, ok: string) => (s === ok ? "ok" : s === "failed" ? "error" : "neutral") as "ok" | "error" | "neutral";

  return (
    <div className="rounded-2xl border border-gray-200 bg-white overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-xs border-collapse">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase tracking-wider">
            {head("title")}
            {showInstitution && <th className="py-3 px-4">{t("columns.institution")}</th>}
            {head("type")}
            {head("year")}
            {head("download", "text-center")}
            {head("extraction", "text-center")}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((doc) => (
            <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
              <td className="py-3.5 px-4 font-semibold text-gray-800">
                {doc.url ? (
                  <a href={externalHref(doc.url)} target="_blank" rel="noreferrer" className="hover:text-emerald-700">
                    {doc.title} ↗
                  </a>
                ) : (
                  doc.title
                )}
              </td>
              {showInstitution && (
                <td className="py-3.5 px-4 text-gray-700">
                  {doc.institution_id ? (
                    <Link href={`/institutions/${doc.institution_id}`} className="text-emerald-700 hover:text-emerald-700">
                      {t("open_institution")}
                    </Link>
                  ) : (
                    <span className="text-gray-500">{t("regional")}</span>
                  )}
                </td>
              )}
              <td className="py-3.5 px-4 text-gray-500">{labels.documentType(doc.document_type)}</td>
              <td className="py-3.5 px-4 font-mono text-gray-700">{doc.period_year ?? MISSING}</td>
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
