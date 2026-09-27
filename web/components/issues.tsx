import type { ReviewIssue } from "@/lib/types";
const labels: Record<string, string> = {
  MISSING_VALUE: "Une valeur est manquante.",
  INVALID_NUMBER: "Le nombre doit être un décimal valide.",
  INVALID_DATE: "La date est invalide.",
  WRONG_DOCUMENT_TYPE: "Ce document ne correspond pas au type attendu.",
  UNSUPPORTED_TAX_BASIS: "La base hors taxes doit être vérifiée.",
  UNSUPPORTED_ADJUSTMENTS: "Des frais ou remises nécessitent une vérification.",
  EXTRACTION_WARNING: "Une incertitude a été signalée lors de la lecture.",
  UNSUPPORTED_CURRENCY: "Cette devise n’est pas prise en charge.",
  LINE_LIMIT: "Le document doit contenir entre 1 et 100 lignes.",
  INVALID_LINE_NUMBER: "Le numéro de ligne est invalide ou répété.",
  UNSUPPORTED_UNIT: "Vérifiez l’unité : pièce, boîte, kg, g, l ou ml.",
  INVALID_SOURCE_PAGE: "La page source est invalide.",
  LINE_TOTAL_MISMATCH:
    "Le total de ligne ne correspond pas à la quantité et au prix.",
  DOCUMENT_TOTAL_MISMATCH:
    "Les totaux du document ne correspondent pas aux lignes.",
  SUPPLIER_MISMATCH: "Les fournisseurs ne correspondent pas.",
  BUYER_MISMATCH: "Les acheteurs ne correspondent pas.",
  SUPPLIER_TAX_ID_MISMATCH: "Les identifiants fiscaux fournisseurs diffèrent.",
  BUYER_TAX_ID_MISMATCH: "Les identifiants fiscaux acheteurs diffèrent.",
  CURRENCY_MISMATCH: "Les devises diffèrent.",
  PO_REFERENCE_MISMATCH: "La référence de commande ne correspond pas.",
  PAIR_CONFIRMATION_REQUIRED:
    "Sans référence de commande, confirmez explicitement l’association des documents.",
  DUPLICATE_SKU: "Une référence produit apparaît plusieurs fois.",
  AMBIGUOUS_DESCRIPTION:
    "La description ne permet pas un rapprochement unique.",
  UNMATCHED_INVOICE_LINE:
    "Cette ligne de facture n’a pas de correspondance certaine.",
  AMBIGUOUS_MATCH: "Plusieurs lignes pourraient correspondre.",
  UNIT_MISMATCH: "Les unités des lignes diffèrent.",
  TAX_RATE_MISMATCH: "Les taux de TVA diffèrent.",
  DESCRIPTION_MISMATCH: "Les descriptions nécessitent une vérification.",
  DUPLICATE_INVOICE: "Cette facture existe déjà dans un autre dossier.",
  MIXED_PRICE_QUANTITY:
    "Les variations de prix et de quantité nécessitent une vérification.",
  REFUSAL: "La lecture automatique n’a pas pu aboutir.",
  TRUNCATED_OUTPUT: "La lecture automatique est incomplète.",
};
export function Issues({ issues }: { issues: ReviewIssue[] }) {
  if (!issues.length) return null;
  return (
    <section className="issue-panel">
      <h2>
        {issues.length} point{issues.length > 1 ? "s" : ""} à vérifier
      </h2>
      <p>
        Aucun brouillon ni montant de demande tant qu’une incertitude subsiste.
      </p>
      <ul>
        {issues.map((issue, i) => (
          <li key={i}>
            <strong>
              {issue.document_role === "PO"
                ? "Commande"
                : issue.document_role === "INVOICE"
                  ? "Facture"
                  : "Association"}
              {issue.line_number ? ` · ligne ${issue.line_number}` : ""}
            </strong>
            <span>
              {labels[issue.code] ||
                "Ce point nécessite une vérification dans le document source."}
            </span>
            <details>
              <summary>Détail du contrôle</summary>
              <p>{issue.message}</p>
              <code>
                {issue.code}
                {issue.field ? ` · ${issue.field}` : ""}
              </code>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
