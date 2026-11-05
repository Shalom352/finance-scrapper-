"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";

type StepId =
  | "overview"
  | "search"
  | "deals"
  | "targeting"
  | "syndication"
  | "institutions"
  | "countries"
  | "financial-data"
  | "documents"
  | "rankings"
  | "analytics"
  | "comparisons"
  | "data-quality"
  | "settings";

type StepHref =
  | "/"
  | "/search"
  | "/deals"
  | "/targeting"
  | "/syndication"
  | "/institutions"
  | "/countries"
  | "/financial-data"
  | "/documents"
  | "/rankings"
  | "/analytics"
  | "/comparisons"
  | "/data-quality"
  | "/settings";

const STEPS: { id: StepId; href: StepHref }[] = [
  { id: "overview", href: "/" },
  { id: "search", href: "/search" },
  { id: "deals", href: "/deals" },
  { id: "targeting", href: "/targeting" },
  { id: "syndication", href: "/syndication" },
  { id: "institutions", href: "/institutions" },
  { id: "countries", href: "/countries" },
  { id: "financial-data", href: "/financial-data" },
  { id: "documents", href: "/documents" },
  { id: "rankings", href: "/rankings" },
  { id: "analytics", href: "/analytics" },
  { id: "comparisons", href: "/comparisons" },
  { id: "data-quality", href: "/data-quality" },
  { id: "settings", href: "/settings" },
];

interface WelcomeGuideProps {
  onClose: () => void;
}

interface TargetBox {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export function WelcomeGuide({ onClose }: WelcomeGuideProps) {
  const t = useTranslations("guide");
  const router = useRouter();
  const pathname = usePathname();
  const [stepIndex, setStepIndex] = useState(0);
  const dialogRef = useRef<HTMLElement>(null);
  const [targetBox, setTargetBox] = useState<TargetBox | null>(null);
  const step = STEPS[stepIndex];

  const descriptions = useMemo(
    () => ({
      overview: { title: t("steps.overview.title"), body: t("steps.overview.body") },
      search: { title: t("steps.search.title"), body: t("steps.search.body") },
      deals: { title: t("steps.deals.title"), body: t("steps.deals.body") },
      targeting: { title: t("steps.targeting.title"), body: t("steps.targeting.body") },
      syndication: { title: t("steps.syndication.title"), body: t("steps.syndication.body") },
      institutions: { title: t("steps.institutions.title"), body: t("steps.institutions.body") },
      countries: { title: t("steps.countries.title"), body: t("steps.countries.body") },
      "financial-data": { title: t("steps.financial_data.title"), body: t("steps.financial_data.body") },
      documents: { title: t("steps.documents.title"), body: t("steps.documents.body") },
      rankings: { title: t("steps.rankings.title"), body: t("steps.rankings.body") },
      analytics: { title: t("steps.analytics.title"), body: t("steps.analytics.body") },
      comparisons: { title: t("steps.comparisons.title"), body: t("steps.comparisons.body") },
      "data-quality": { title: t("steps.data_quality.title"), body: t("steps.data_quality.body") },
      settings: { title: t("steps.settings.title"), body: t("steps.settings.body") },
    }),
    [t],
  );
  const description = descriptions[step.id];

  const updateTargetBox = useCallback(() => {
    const element = document.querySelector<HTMLElement>(`[data-guide="${step.id}"]`);
    if (!element) {
      setTargetBox(null);
      return false;
    }
    const bounds = element.getBoundingClientRect();
    setTargetBox({
      top: Math.max(0, bounds.top),
      left: Math.max(0, bounds.left),
      right: Math.min(window.innerWidth, bounds.right),
      bottom: Math.min(window.innerHeight, bounds.bottom),
      width: Math.min(window.innerWidth, bounds.right) - Math.max(0, bounds.left),
      height: Math.min(window.innerHeight, bounds.bottom) - Math.max(0, bounds.top),
    });
    return true;
  }, [step.id]);

  useEffect(() => {
    setTargetBox(null);
    if (pathname !== step.href) {
      router.replace(step.href);
      return;
    }

    let attempts = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let animationFrame = 0;
    const locate = () => {
      const element = document.querySelector<HTMLElement>(`[data-guide="${step.id}"]`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
        animationFrame = window.requestAnimationFrame(updateTargetBox);
        return;
      }
      if (attempts < 20) {
        attempts += 1;
        retryTimer = setTimeout(locate, 250);
      }
    };
    locate();

    const handleGeometryChange = () => updateTargetBox();
    window.addEventListener("scroll", handleGeometryChange, true);
    window.addEventListener("resize", handleGeometryChange);
    const resizeObserver = new ResizeObserver(handleGeometryChange);
    resizeObserver.observe(document.documentElement);

    return () => {
      if (retryTimer) clearTimeout(retryTimer);
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("scroll", handleGeometryChange, true);
      window.removeEventListener("resize", handleGeometryChange);
      resizeObserver.disconnect();
    };
  }, [pathname, router, step.href, step.id, updateTargetBox]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const focusableButtons = () => Array.from(dialog?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    focusableButtons()[0]?.focus();
    const handleKeyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const buttons = focusableButtons();
      if (buttons.length === 0) return;
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyboard);
    return () => window.removeEventListener("keydown", handleKeyboard);
  }, [onClose]);

  const goTo = (nextIndex: number) => {
    if (nextIndex < 0) return;
    if (nextIndex >= STEPS.length) {
      onClose();
      return;
    }
    setStepIndex(nextIndex);
  };

  const gap = 10;
  const cutout = targetBox
    ? {
        top: Math.max(0, targetBox.top - gap),
        left: Math.max(0, targetBox.left - gap),
        right: Math.min(window.innerWidth, targetBox.right + gap),
        bottom: Math.min(window.innerHeight, targetBox.bottom + gap),
      }
    : null;
  const panelStyle: React.CSSProperties = { background: "rgba(15, 23, 42, 0.58)" };

  return (
    <div className="fixed inset-0 z-[70]" aria-hidden="false">
      {!cutout ? (
        <div className="absolute inset-0" style={panelStyle} />
      ) : (
        <>
          <div className="absolute left-0 right-0 top-0" style={{ ...panelStyle, height: cutout.top }} />
          <div
            className="absolute left-0"
            style={{ ...panelStyle, top: cutout.top, width: cutout.left, height: cutout.bottom - cutout.top }}
          />
          <div
            className="absolute right-0"
            style={{ ...panelStyle, top: cutout.top, left: cutout.right, height: cutout.bottom - cutout.top }}
          />
          <div className="absolute bottom-0 left-0 right-0" style={{ ...panelStyle, top: cutout.bottom }} />
          <div
            aria-hidden="true"
            className="pointer-events-auto absolute rounded-2xl ring-4 ring-emerald-400 ring-offset-2 ring-offset-transparent shadow-[0_0_0_2px_rgba(255,255,255,0.9)]"
            style={{ top: cutout.top, left: cutout.left, width: cutout.right - cutout.left, height: cutout.bottom - cutout.top }}
          />
        </>
      )}

      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-guide-title"
        className="fixed bottom-4 left-1/2 z-[71] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 rounded-2xl border border-white/20 bg-white p-5 shadow-2xl sm:bottom-6 sm:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">{t("eyebrow")}</p>
            <h2 id="welcome-guide-title" className="mt-2 text-xl font-bold text-gray-900 sm:text-2xl">
              {description.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-emerald-600"
            aria-label={t("close")}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>

        <p className="mt-3 text-sm leading-6 text-gray-600">{description.body}</p>
        {!targetBox && (
          <p className="mt-3 text-xs text-gray-500" role="status">
            {t("target_loading")}
          </p>
        )}

        <div className="mt-5 flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-gray-500">
              {t("step_count", { current: stepIndex + 1, total: STEPS.length })}
            </p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100" aria-hidden="true">
              <div
                className="h-full rounded-full bg-emerald-600 transition-all"
                style={{ width: `${((stepIndex + 1) / STEPS.length) * 100}%` }}
              />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="hidden rounded-lg px-3 py-2 text-sm font-medium text-gray-500 hover:bg-gray-100 sm:inline-flex"
            >
              {t("skip")}
            </button>
            <button
              type="button"
              onClick={() => goTo(stepIndex - 1)}
              disabled={stepIndex === 0}
              className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {t("previous")}
            </button>
            <button
              type="button"
              onClick={() => goTo(stepIndex + 1)}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2"
            >
              {stepIndex === STEPS.length - 1 ? t("finish") : t("next")}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
