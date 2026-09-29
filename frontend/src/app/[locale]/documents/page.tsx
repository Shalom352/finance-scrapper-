"use client";

import React, { useEffect, useState } from "react";
import { Link } from "@/i18n/navigation";
import type { Document } from "@/types";
import { getDocuments } from "@/lib/api";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState("");
  const [selectedYear, setSelectedYear] = useState("");

  useEffect(() => {
    let isCancelled = false;

    getDocuments({
      page,
      page_size: pageSize,
      document_type: selectedType || undefined,
      period_year: selectedYear ? Number(selectedYear) : undefined,
    })
      .then((res) => {
        if (!isCancelled) {
          setDocuments(res.items || []);
          setTotal(res.total || 0);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setDocuments([]);
          setTotal(0);
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [page, pageSize, selectedType, selectedYear]);

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
            Centre Documentaire Officiel
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Rapports annuels, bilans comptables et publications de supervision BCEAO / CB-UMOA.
          </p>
        </div>
        <div className="text-xs font-semibold text-gray-300">
          <span className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-900/60">
            {total} document{total > 1 ? "s" : ""} référencé{total > 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <div>
          <label className="text-[11px] text-gray-400 block mb-1 font-medium">Type de document</label>
          <select
            value={selectedType}
            onChange={(e) => {
              setSelectedType(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">Tous les types</option>
            <option value="annual_report">Rapport Annuel Audité</option>
            <option value="financial_statement">États Financiers Synthétiques</option>
            <option value="regulatory_report">Rapport de Supervision Réglementaire</option>
            <option value="press_release">Communiqué Financier</option>
          </select>
        </div>

        <div>
          <label className="text-[11px] text-gray-400 block mb-1 font-medium">Exercice Comptable</label>
          <select
            value={selectedYear}
            onChange={(e) => {
              setSelectedYear(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">Toutes les années</option>
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2022">2022</option>
            <option value="2021">2021</option>
          </select>
        </div>
      </div>

      {/* Results Table */}
      {loading ? (
        <TableSkeleton rows={8} cols={6} />
      ) : documents.length === 0 ? (
        <EmptyState
          title="Aucun document trouvé"
          description="Aucune publication ne correspond aux critères de filtre sélectionnés."
        />
      ) : (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Titre du Document</th>
                  <th className="py-3 px-4">Établissement</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Exercice</th>
                  <th className="py-3 px-4 text-center">Téléchargement</th>
                  <th className="py-3 px-4 text-center">Extraction PDF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-gray-200">
                      <div>{doc.title}</div>
                      {doc.source?.name && (
                        <span className="text-[11px] text-gray-400 block font-normal">
                          Source : {doc.source.name}
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-gray-300">
                      {doc.institution_id ? (
                        <Link
                          href={`/institutions/${doc.institution_id}`}
                          className="hover:text-emerald-400 text-emerald-400/90 font-medium"
                        >
                          {doc.institution?.name_official || doc.institution?.name || "Voir l'institution →"}
                        </Link>
                      ) : (
                        <span className="text-gray-500">Régional (UMOA)</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-gray-400 capitalize">
                      {doc.document_type.replace(/_/g, " ")}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-gray-300">
                      {doc.period_year || "—"}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <StatusBadge
                        status={doc.download_status === "downloaded" ? "verified" : "needs_review"}
                        size="sm"
                      />
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <StatusBadge
                        status={doc.extraction_status === "extracted" ? "verified" : "needs_review"}
                        size="sm"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            currentPage={page}
            pageSize={pageSize}
            total={total}
            onPageChange={(p) => setPage(p)}
          />
        </div>
      )}
    </div>
  );
}
