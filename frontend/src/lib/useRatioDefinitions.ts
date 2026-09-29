"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import type { RatioDefinition } from "@/types";
import { getRatioDefinitions } from "@/lib/api";

/**
 * Ratio labels come from the backend catalogue (RATIO_DEFINITIONS name_fr / name_en):
 * single source of truth, no duplicated labels in the dictionaries. Loaded once per session.
 */
let cache: Promise<RatioDefinition[]> | null = null;

function loadDefinitions(): Promise<RatioDefinition[]> {
  if (!cache) {
    cache = getRatioDefinitions().catch(() => {
      cache = null; // allow a later retry
      return [];
    });
  }
  return cache;
}

/** Test hook: forget the cached catalogue. */
export function resetRatioDefinitionsCache() {
  cache = null;
}

export function useRatioDefinitions() {
  const locale = useLocale();
  const [definitions, setDefinitions] = useState<RatioDefinition[]>([]);

  useEffect(() => {
    let cancelled = false;
    loadDefinitions().then((defs) => !cancelled && setDefinitions(defs));
    return () => {
      cancelled = true;
    };
  }, []);

  /** User-facing ratio name for the active locale; the code only if the catalogue is unavailable. */
  const ratioName = (code: string) => {
    const d = definitions.find((x) => x.ratio_code === code);
    return d ? (locale === "en" ? d.name_en : d.name_fr) : code;
  };

  return { definitions, ratioName };
}
