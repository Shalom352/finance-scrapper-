"use client";

import React, { useEffect, useState } from "react";
import { Link } from "@/i18n/navigation";
import type { Institution } from "@/types";
import { getInstitutions } from "@/lib/api";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";

const UMOA_COUNTRIES = [
  { code: "BJ", label: "Bénin" },
  { code: "BF", label: "Burkina Faso" },
  { code: "CI", label: "Côte d'Ivoire" },
  { code: "GW", label: "Guinée-Bissau" },
  { code: "ML", label: "Mali" },
  { code: "NE", label: "Niger" },
  { code: "SN", label: "Sénégal" },
  { code: "TG", label: "Togo" },
];

export default function InstitutionsListPage() {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");

  useEffect(() => {
    let isCancelled = false;

    getInstitutions({
      page,
      page_size: pageSize,
      country_code: selectedCountry || undefined,
      status: selectedStatus || undefined,
      search: search.trim() || undefined,
    })
      .then((res) => {
        if (!isCancelled) {
          setInstitutions(res.items || []);
          setTotal(res.total || 0);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setInstitutions([]);
          setTotal(0);
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [page, pageSize, selectedCountry, selectedStatus, search]);

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
            Répertoire des Institutions Bancaires
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Établissements de crédit et institutions financières agréées dans les 8 pays de l&apos;UMOA.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-300">
          <span className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-900/60">
            {total} établissement{total > 1 ? "s" : ""} référencé{total > 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <div>
          <label className="text-[11px] text-gray-400 block mb-1 font-medium">Recherche</label>
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Nom d'établissement ou mot-clé..."
            className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="text-[11px] text-gray-400 block mb-1 font-medium">Pays UMOA</label>
          <select
            value={selectedCountry}
            onChange={(e) => {
              setSelectedCountry(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">Tous les pays (8)</option>
            {UMOA_COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label} ({c.code})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[11px] text-gray-400 block mb-1 font-medium">Statut d&apos;activité</label>
          <select
            value={selectedStatus}
            onChange={(e) => {
              setSelectedStatus(e.target.value);
              setPage(1);
            }}
            className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">Tous les statuts</option>
            <option value="active">Actif</option>
            <option value="closed">Fermé</option>
            <option value="in_liquidation">En liquidation</option>
          </select>
        </div>
      </div>

      {/* Table / Results */}
      {loading ? (
        <TableSkeleton rows={8} cols={5} />
      ) : institutions.length === 0 ? (
        <EmptyState
          title="Aucune institution trouvée"
          description="Aucun établissement ne correspond aux filtres sélectionnés. Essayez d'élargir votre recherche."
          actionText="Réinitialiser les filtres"
          onAction={() => {
            setSearch("");
            setSelectedCountry("");
            setSelectedStatus("");
            setPage(1);
          }}
        />
      ) : (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Établissement</th>
                  <th className="py-3 px-4">Pays</th>
                  <th className="py-3 px-4">Groupe Bancaire</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4 text-center">Statut</th>
                  <th className="py-3 px-4 text-right">Fiche</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {institutions.map((inst) => {
                  const instName = inst.name_official || inst.name || "Institution";
                  const countryCode = inst.country?.iso_code_2 || inst.country?.code || "";

                  return (
                    <tr key={inst.id} className="hover:bg-gray-800/30 transition-colors group">
                      <td className="py-3.5 px-4 font-bold text-gray-200">
                        <Link
                          href={`/institutions/${inst.id}`}
                          className="hover:text-emerald-400 transition-colors block"
                        >
                          {instName}
                        </Link>
                        {inst.name_commercial && (
                          <span className="text-[11px] text-gray-400 block font-normal">
                            {inst.name_commercial}
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-gray-300">
                        <span className="font-semibold text-emerald-400 mr-1.5">{countryCode}</span>
                        <span>{inst.country?.name_fr || countryCode}</span>
                      </td>
                      <td className="py-3.5 px-4 text-gray-400">
                        {inst.banking_group?.name || "—"}
                      </td>
                      <td className="py-3.5 px-4 text-gray-400 capitalize">
                        {inst.institution_type || "Banque universelle"}
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <StatusBadge status={inst.status === "active" ? "verified" : "needs_review"} size="sm" />
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <Link
                          href={`/institutions/${inst.id}`}
                          className="px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-800/60 group-hover:border-emerald-500/50 group-hover:bg-emerald-600 text-gray-300 group-hover:text-white transition-all text-xs font-semibold"
                        >
                          Consulter →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
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
