"use client";

import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { ApiError, errorText } from "@/lib/api";
import { states } from "@/lib/format";
import type { Status } from "@/lib/types";
import Link from "next/link";

export function Badge({ status }: { status: Status }) {
  const state = states[status];
  return (
    <span className={`badge ${state.tone}`}>
      <i />
      {state.label}
    </span>
  );
}
export function Loading({
  label = "Chargement du dossier…",
}: {
  label?: string;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      {label}
    </div>
  );
}
export function ErrorNotice({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const existing =
    error instanceof ApiError &&
    error.details &&
    typeof error.details === "object" &&
    "existing_case_id" in error.details
      ? String(error.details.existing_case_id)
      : null;
  return (
    <div className="error-notice" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>{errorText(error)}</strong>
        {error instanceof ApiError && error.requestId && (
          <small>Référence : {error.requestId}</small>
        )}
        {existing && (
          <Link href={`/dossiers/${existing}`}>
            Ouvrir le dossier existant →
          </Link>
        )}
      </div>
      {onRetry && (
        <button className="button secondary small" onClick={onRetry}>
          <RefreshCw size={15} /> Réessayer
        </button>
      )}
    </div>
  );
}
