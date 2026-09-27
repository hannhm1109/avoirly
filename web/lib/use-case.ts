"use client";
import { useCallback, useEffect, useState } from "react";
import { getCase } from "./api";
import type { CaseDetail } from "./types";
export function useCase(id: string) {
  const [data, setData] = useState<CaseDetail | null>(null),
    [error, setError] = useState<unknown>(null);
  const load = useCallback(async () => {
    try {
      const value = await getCase(id);
      setData(value);
      setError(null);
      return value;
    } catch (e) {
      setError(e);
      return null;
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);
  const active =
    data?.status === "PROCESSING" ||
    data?.processing_step === "QUEUED" ||
    data?.status === "DISCREPANCY_FOUND";
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [active, load]);
  return { data, error, load, active };
}
