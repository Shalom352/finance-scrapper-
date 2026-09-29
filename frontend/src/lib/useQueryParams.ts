"use client";

import { useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { usePathname, useRouter } from "@/i18n/navigation";
import { buildLocaleHref } from "@/lib/url";

/**
 * Page state (filters, pagination, year, search) stored in the URL query string,
 * so it survives reloads and locale switches. Components using this hook must be
 * rendered under a <Suspense> boundary (Next 16 useSearchParams requirement).
 */
export function useQueryParams() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const get = useCallback((key: string): string => searchParams.get(key) ?? "", [searchParams]);

  const set = useCallback(
    (updates: Record<string, string | number | null | undefined>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === undefined || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      router.replace(buildLocaleHref(pathname, next), { scroll: false });
    },
    [searchParams, router, pathname],
  );

  return { get, set, searchParams };
}
