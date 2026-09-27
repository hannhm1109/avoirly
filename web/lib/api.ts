import type { CaseDetail, CasePage, CaseSummary } from "./types";

const messages: Record<string, string> = {
  VERSION_CONFLICT: "Ce dossier a changé. Rechargez-le avant de réessayer.",
  DUPLICATE_FILE: "Ce document est déjà associé à un dossier.",
  IDEMPOTENCY_CONFLICT:
    "Cette demande existe déjà avec des informations différentes. Rechargez le dossier.",
  OWNER_BUSY:
    "Une analyse est déjà en cours. Attendez sa fin avant de continuer.",
  MISSING_MODEL:
    "L’extraction automatique n’est pas configurée. Vérifiez les paramètres du serveur ou renseignez les données à partir des documents.",
  MISSING_API_KEY:
    "L’extraction automatique nécessite une clé API configurée sur le serveur.",
  FILE_SIZE: "Le document doit être non vide et ne pas dépasser 10 Mo.",
  WRONG_MIME: "Format non reconnu. Choisissez un PDF, PNG ou JPEG valide.",
  PAGE_LIMIT: "Un PDF peut contenir jusqu’à 10 pages.",
  PIXEL_LIMIT: "Une image peut contenir jusqu’à 25 mégapixels.",
  ENCRYPTED_PDF:
    "Ce PDF est protégé par un mot de passe. Importez une copie déverrouillée.",
  INVALID_INPUT: "Vérifiez les champs du formulaire.",
  NOT_FOUND: "Ce dossier ou ce document n’est plus disponible.",
  NETWORK_ERROR:
    "L’extraction a été interrompue. Vous pouvez relancer le traitement.",
  CASE_PROCESSING:
    "L’analyse est en cours. Attendez sa fin avant de modifier les documents.",
  CASE_CLOSED: "Ce dossier est clôturé.",
  UNSUPPORTED_MAPPING:
    "Ces lignes ne respectent pas les règles de rapprochement. Vérifiez les références et les unités.",
};
export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    public details: unknown,
    public requestId?: string,
  ) {
    super(
      messages[code] ||
        "Une erreur est survenue. Réessayez ou rechargez le dossier.",
    );
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: init.signal || AbortSignal.timeout(30000),
    });
  } catch {
    throw new ApiError("NETWORK_UNAVAILABLE", 0, null);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      data.code || "SERVER_UNAVAILABLE",
      response.status,
      data.details,
      data.request_id,
    );
  }
  return response.json() as Promise<T>;
}
export const getCases = (offset = 0) =>
  api<CasePage>(`/cases?limit=20&offset=${offset}`);
export const getCase = (id: string) =>
  api<CaseDetail>(`/cases/${encodeURIComponent(id)}`);
export const createCase = () => api<CaseSummary>("/cases", { method: "POST" });
export function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Une erreur est survenue.";
}

export async function analyzeCase(
  id: string,
  version: number,
  retry = false,
  language = "fr",
) {
  // Persist only the request key/version, never document data. A network retry reuses the key.
  const slot = `avoirly-request:${id}:${retry ? "retry" : "analyze"}:${version}:${language}`;
  let requestKey = sessionStorage.getItem(slot);
  if (!requestKey) {
    requestKey = crypto.randomUUID();
    sessionStorage.setItem(slot, requestKey);
  }
  const result = await api<{
    job_id: string;
    case_id: string;
    version: number;
  }>(`/cases/${id}/${retry ? "retry" : "analyze"}`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey },
    body: JSON.stringify({ expected_version: version, language }),
  });
  sessionStorage.removeItem(slot);
  return result;
}
