import type { Status } from "./types";

export const states: Record<Status, { label: string; tone: string }> = {
  PENDING: { label: "À analyser", tone: "neutral" },
  PROCESSING: { label: "Analyse en cours", tone: "blue" },
  NEEDS_REVIEW: { label: "À vérifier", tone: "amber" },
  NO_DISCREPANCY: { label: "Aucun écart", tone: "green" },
  DISCREPANCY_FOUND: { label: "Écart détecté", tone: "green" },
  CLAIM_DRAFTED: { label: "Brouillon prêt", tone: "green" },
  FAILED: { label: "Analyse interrompue", tone: "red" },
  CLOSED: { label: "Clôturé", tone: "neutral" },
};
// Format strings without converting monetary values to binary floating point.
export function money(
  value: string | null | undefined,
  currency: string | null = "MAD",
) {
  if (value == null) return "—";
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return "—";
  const integer = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  const fraction = (match[3] || "").padEnd(2, "0");
  return `${match[1]}${integer},${fraction}${currency ? ` ${currency}` : ""}`;
}
export function quantity(value: string | null) {
  return value?.replace(".", ",") ?? "—";
}
export function dateLabel(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}
