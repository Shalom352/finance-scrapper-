"use client";

import React, { useEffect, useState, use, Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { useSearchParams } from "next/navigation";
import type { SearchResults } from "@/types";
import { searchGlobal } from "@/lib/api";
import { StatusBadge } from "@/components/common/StatusBadge";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";

interface PageProps {
  params: Promise<{ locale: string }>;
}

export default function SearchPage({ params }: PageProps) {
  use(params);
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={3} />}>
      <SearchContent />
    </Suspense>
  );
}

function SearchContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(Boolean(initialQuery.trim()));

  useEffect(() => {
    if (!initialQuery.trim()) return;

    searchGlobal(initialQuery.trim())
      .then((res) => {
        setResults(res);
        setLoading(false);
      })
      .catch(() => {
        setResults(null);
        setLoading(false);
      });
  }, [initialQuery]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    searchGlobal(query.trim())
      .then((res) => {
        setResults(res);
        setLoading(false);
      })
      .catch(() => {
        setResults(null);
        setLoading(false);
      });
  };

  const hasResults =
    results &&
    (results.institutions.length > 0 ||
      results.documents.length > 0 ||
      results.sources.length > 0 ||
      (results.metrics && results.metrics.length > 0));

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
          Recherche Globale
        </h1>
        <p className="text-xs text-gray-400 mt-1">
          Explorez simultanément les banques, documents officiels, sources et métriques financières.
        </p>
      </div>

      {/* Search Input Box */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ex: Société Générale, BCEAO, Total Actifs, ROA, Côte d'Ivoire..."
          className="flex-1 px-4 py-3 rounded-2xl border border-gray-800 bg-gray-900/60 text-sm text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:bg-gray-900 focus:outline-none transition-all shadow-inner"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-6 py-3 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors disabled:opacity-50 shadow-md"
        >
          {loading ? "Recherche..." : "Rechercher"}
        </button>
      </form>

      {/* Results Section */}
      {loading ? (
        <TableSkeleton rows={6} cols={3} />
      ) : !hasResults && query.trim() ? (
        <EmptyState
          title="Aucun résultat trouvé"
          description={`Aucune donnée ne correspond au terme "${query}". Vérifiez l'orthographe ou essayez un mot-clé plus générique.`}
        />
      ) : results ? (
        <div className="space-y-8">
          {/* Institutions Section */}
          {results.institutions.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>🏛️ Institutions trouvées</span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 text-xs border border-emerald-800">
                  {results.institutions.length}
                </span>
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {results.institutions.map((inst) => (
                  <Link
                    key={inst.id}
                    href={`/institutions/${inst.id}`}
                    className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 hover:border-emerald-500/50 hover:bg-gray-900 transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-bold text-gray-200 text-xs truncate max-w-[200px]">
                          {inst.name_official || inst.name}
                        </span>
                        <StatusBadge status={inst.status === "active" ? "verified" : "needs_review"} size="sm" />
                      </div>
                      {inst.name_commercial && (
                        <span className="text-[11px] text-emerald-400 font-medium block">
                          {inst.name_commercial}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-800 text-[11px] text-gray-500">
                      <span>{inst.country?.name_fr || "UMOA"}</span>
                      <span className="text-emerald-400 font-semibold">Fiche →</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Documents Section */}
          {results.documents.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>📑 Documents officiels trouvés</span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 text-xs border border-emerald-800">
                  {results.documents.length}
                </span>
              </h3>

              <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase">
                      <th className="py-3 px-4">Titre</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Année</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {results.documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-gray-800/30 transition-colors">
                        <td className="py-3 px-4 font-semibold text-gray-200">{doc.title}</td>
                        <td className="py-3 px-4 text-gray-400 capitalize">{doc.document_type.replace(/_/g, " ")}</td>
                        <td className="py-3 px-4 font-mono text-gray-300">{doc.period_year || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Metrics Section */}
          {results.metrics && results.metrics.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>📊 Métriques financières du catalogue</span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 text-xs border border-emerald-800">
                  {results.metrics.length}
                </span>
              </h3>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.metrics.map((m) => (
                  <div key={m.code} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono font-bold text-emerald-400">{m.code}</span>
                      <span className="px-2 py-0.5 rounded bg-gray-800 text-[10px] text-gray-400 uppercase">
                        {m.category}
                      </span>
                    </div>
                    <div className="font-semibold text-gray-200 mb-1">{m.label_fr}</div>
                    <p className="text-[11px] text-gray-400 leading-relaxed">{m.definition_fr}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
