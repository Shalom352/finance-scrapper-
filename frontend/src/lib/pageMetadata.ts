import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

/**
 * Tab title of a section: its menu label, completed by the root template ("Transactions — UMOA Banking
 * Intelligence"). History, bookmarks and screen readers tell the pages apart (audit 22/10/2026).
 */
export function sectionMetadata(navKey: string) {
  return async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
    const { locale } = await params;
    const t = await getTranslations({ locale, namespace: "nav" });
    return { title: t(navKey) };
  };
}
