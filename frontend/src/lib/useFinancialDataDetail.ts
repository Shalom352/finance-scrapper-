"use client";

import { useCallback, useEffect, useState } from "react";
import type { FinancialDataDetail } from "@/types";
import { getFinancialDataById } from "@/lib/api";

type DetailState =
  | { status: "idle" | "loading"; data: null }
  | { status: "error"; data: null }
  | { status: "ready"; data: FinancialDataDetail };

/** Loads the real financial data record (with provenance) from `GET /api/v1/financial-data/{id}`. */
export function useFinancialDataDetail(id: string | null) {
  const [state, setState] = useState<DetailState>({ status: "idle", data: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading state must reset when id changes
    setState({ status: "loading", data: null });
    getFinancialDataById(id)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, retry };
}
