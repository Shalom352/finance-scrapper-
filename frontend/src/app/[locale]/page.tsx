import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

// UMOA member countries with official data
const UMOA_COUNTRIES = [
  { code: "BJ", name_fr: "Bénin", name_en: "Benin", flag: "🇧🇯", capital: "Cotonou" },
  { code: "BF", name_fr: "Burkina Faso", name_en: "Burkina Faso", flag: "🇧🇫", capital: "Ouagadougou" },
  { code: "CI", name_fr: "Côte d'Ivoire", name_en: "Côte d'Ivoire", flag: "🇨🇮", capital: "Abidjan" },
  { code: "GW", name_fr: "Guinée-Bissau", name_en: "Guinea-Bissau", flag: "🇬🇼", capital: "Bissau" },
  { code: "ML", name_fr: "Mali", name_en: "Mali", flag: "🇲🇱", capital: "Bamako" },
  { code: "NE", name_fr: "Niger", name_en: "Niger", flag: "🇳🇪", capital: "Niamey" },
  { code: "SN", name_fr: "Sénégal", name_en: "Senegal", flag: "🇸🇳", capital: "Dakar" },
  { code: "TG", name_fr: "Togo", name_en: "Togo", flag: "🇹🇬", capital: "Lomé" },
] as const;

export default function HomePage() {
  const t = useTranslations("home");
  const tCommon = useTranslations("common");
  const tFooter = useTranslations("footer");

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Navigation */}
      <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-sm font-bold">
                U
              </div>
              <span className="font-semibold text-white tracking-tight">
                UMOA Banking Intelligence
              </span>
            </div>
            <div className="flex items-center gap-1">
              <LocaleSwitcher />
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-emerald-950/20 to-gray-950 pointer-events-none" />
        <div className="absolute top-20 left-1/4 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 right-1/4 w-64 h-64 bg-teal-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 md:py-32">
          <div className="max-w-3xl">
            {/* Phase badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm mb-8">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              {t("status.phase")}
            </div>

            <h1 className="text-4xl md:text-6xl font-bold text-white mb-6 leading-tight">
              {t("hero.title")}
            </h1>
            <p className="text-xl text-emerald-400 font-medium mb-4">
              {t("hero.subtitle")}
            </p>
            <p className="text-gray-400 text-lg mb-10 leading-relaxed">
              {t("hero.description")}
            </p>
            <div className="flex flex-wrap gap-4">
              <button
                disabled
                className="px-6 py-3 rounded-xl bg-emerald-600/50 text-emerald-300 border border-emerald-600/30 cursor-not-allowed text-sm font-medium"
              >
                {t("hero.cta_explore")}
                <span className="ml-2 text-xs opacity-60">(Phase 1)</span>
              </button>
              <a
                href="#status"
                className="px-6 py-3 rounded-xl border border-gray-700 text-gray-300 hover:border-gray-600 hover:text-white transition-colors text-sm font-medium"
              >
                {t("hero.cta_learn")}
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Countries */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="mb-12">
          <h2 className="text-2xl font-bold text-white mb-2">
            {t("countries.title")}
          </h2>
          <p className="text-gray-400">{t("countries.subtitle")}</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          {UMOA_COUNTRIES.map((country) => (
            <div
              key={country.code}
              className="group flex flex-col items-center gap-2 p-4 rounded-xl border border-gray-800 bg-gray-900/50 hover:border-gray-700 hover:bg-gray-900 transition-all"
            >
              <span className="text-3xl">{country.flag}</span>
              <span className="text-xs text-gray-400 text-center font-medium group-hover:text-gray-300 transition-colors">
                {country.name_fr}
              </span>
              <span className="text-xs text-gray-600 font-mono">{country.code}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Status */}
      <section id="status" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="rounded-2xl border border-gray-800 bg-gray-900/50 p-8 md:p-12">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0 mt-1">
              <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold text-white mb-3">{t("status.title")}</h2>
              <p className="text-gray-400 mb-4 leading-relaxed">{t("status.description")}</p>
              <p className="text-sm text-emerald-400">{t("status.sources")}</p>

              {/* Pipeline visualization */}
              <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Foundation", phase: "Phase 0", status: "active" },
                  { label: "Référentiels", phase: "Phase 1", status: "pending" },
                  { label: "Documents", phase: "Phase 2", status: "pending" },
                  { label: "Dashboard", phase: "Phase 3+", status: "pending" },
                ].map((item) => (
                  <div
                    key={item.phase}
                    className={`p-4 rounded-xl border ${
                      item.status === "active"
                        ? "border-emerald-500/30 bg-emerald-500/5"
                        : "border-gray-800 bg-gray-900/30"
                    }`}
                  >
                    <div className={`text-xs font-mono mb-1 ${item.status === "active" ? "text-emerald-400" : "text-gray-600"}`}>
                      {item.phase}
                    </div>
                    <div className={`text-sm font-medium ${item.status === "active" ? "text-white" : "text-gray-500"}`}>
                      {item.label}
                    </div>
                    {item.status === "active" && (
                      <div className="mt-2 w-full h-1 bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-500 rounded-full w-1/2 animate-pulse" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-6 h-6 rounded bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-xs font-bold">
                U
              </div>
              <span className="text-sm text-gray-500 font-medium">UMOA Banking Intelligence</span>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-600 max-w-sm">{tFooter("disclaimer")}</p>
              <p className="text-xs text-gray-700 mt-1">{tFooter("sources")}</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

// ============================================================
// Locale Switcher Component
// ============================================================

function LocaleSwitcher() {
  return (
    <div className="flex items-center gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800">
      <a
        href="/fr"
        className="px-2 py-1 text-xs rounded font-medium text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
      >
        FR
      </a>
      <a
        href="/en"
        className="px-2 py-1 text-xs rounded font-medium text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
      >
        EN
      </a>
    </div>
  );
}
