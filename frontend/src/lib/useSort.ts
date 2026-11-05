"use client";

import { useCallback, useMemo, useState } from "react";

export type SortDir = "asc" | "desc";
export type SortValue = string | number | null | undefined;
export type SortAccessors<T, K extends string> = Record<K, (item: T) => SortValue>;

/** ISO date / datetime string → epoch ms; anything unparseable is null (sorted last). */
export function dateKey(value: string | null | undefined): number | null {
  if (!value) return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

function compare(a: SortValue, b: SortValue): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "fr", { sensitivity: "base", numeric: true });
}

/**
 * Client-side sort of the rows already loaded (filtered and paginated by the caller).
 * Missing values always go last, whatever the direction. The sort never touches the URL,
 * so filters and the current page are preserved.
 */
export function useSort<T, K extends string>(
  items: readonly T[],
  accessors: SortAccessors<T, K>,
  initial: { key: NoInfer<K>; dir: SortDir },
) {
  const [sortKey, setSortKey] = useState<K>(initial.key);
  const [dir, setDir] = useState<SortDir>(initial.dir);

  const sorted = useMemo(() => {
    const get = accessors[sortKey];
    if (!get) return [...items];
    const sign = dir === "asc" ? 1 : -1;
    return items
      .map((item, index) => ({ item, index, v: get(item) }))
      .sort((x, y) => {
        const xMissing = x.v === null || x.v === undefined || x.v === "";
        const yMissing = y.v === null || y.v === undefined || y.v === "";
        if (xMissing || yMissing) return xMissing === yMissing ? x.index - y.index : xMissing ? 1 : -1;
        return sign * compare(x.v, y.v) || x.index - y.index;
      })
      .map((e) => e.item);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- accessors are static per table
  }, [items, sortKey, dir]);

  /** Same column: flip direction. New column: dates and numbers start descending, text ascending. */
  const toggle = useCallback(
    (key: K, firstDir: SortDir = "asc") => {
      if (key === sortKey) {
        setDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setDir(firstDir);
      }
    },
    [sortKey],
  );

  const setSort = useCallback((key: K, nextDir: SortDir) => {
    setSortKey(key);
    setDir(nextDir);
  }, []);

  return { sorted, sortKey, dir, toggle, setSort };
}
