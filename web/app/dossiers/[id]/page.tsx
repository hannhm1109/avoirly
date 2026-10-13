"use client";
import { useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  Trash2,
  CheckCircle2,
} from "lucide-react";
import { api, analyzeCase } from "@/lib/api";
import { useCase } from "@/lib/use-case";
import { money, quantity, dateLabel } from "@/lib/format";
import type { Role, CaseSummary } from "@/lib/types";
import { Badge, ErrorNotice, Loading } from "@/components/ui";
import { Issues } from "@/components/issues";
import { DraftEditor } from "@/components/draft-editor";
import { UploadSlot, uploadFile } from "@/components/upload";
import { RecoveryTracker } from "@/components/recovery-tracker";

export default function CasePage() {
  const { id } = useParams<{ id: string }>(),
    router = useRouter(),
    { data, error, load, active } = useCase(id);
  const [busy, setBusy] = useState(false),
    [draftDirty, setDraftDirty] = useState(false),
    [actionError, setActionError] = useState<unknown>(null),
    [files, setFiles] = useState<Partial<Record<Role, File>>>({}),
    [replace, setReplace] = useState(false),
    [reason, setReason] = useState("EXPORTED"),
    [confirmDelete, setConfirmDelete] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!data)
    return error ? (
      <ErrorNotice error={error} onRetry={() => void load()} />
    ) : (
      <Loading />
    );
  const invoice =
    data.extractions.INVOICE?.corrected || data.extractions.INVOICE?.raw;
  const complete = !!data.documents.PO && !!data.documents.INVOICE,
    closed = data.status === "CLOSED",
    editable = !active && !closed && !data.recovery.has_sent_record;
  const result = data.comparison,
    eligible = [
      "CLAIM_DRAFTED",
      "DISCREPANCY_FOUND",
      "NO_DISCREPANCY",
      "CLAIM_SENT",
      "AWAITING_RESPONSE",
      "CREDIT_PROMISED",
      "CREDIT_CONFIRMED",
    ].includes(data.status);
  return (
    <>
      <Link className="back-link" href="/">
        <ArrowLeft size={16} /> Mes dossiers
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">DOSSIER {id.slice(0, 8)}</div>
          <h1>{invoice?.supplier?.name || "Votre rapprochement"}</h1>
          <p>
            {invoice?.document_number
              ? `Facture ${invoice.document_number} · `
              : ""}
            Mis à jour le {dateLabel(data.updated_at)}
          </p>
        </div>
        <Badge status={data.status} />
      </div>
      <ol className="progress-strip">
        <li className={complete ? "done" : ""}>1. Documents</li>
        <li className={eligible ? "done" : ""}>2. Vérification</li>
        <li className={eligible ? "done" : ""}>3. Résultat</li>
        <li
          className={data.draft || data.recovery.has_sent_record ? "done" : ""}
        >
          4. Brouillon
        </li>
        <li className={data.recovery.has_sent_record ? "done" : ""}>
          5. Suivi
        </li>
      </ol>
      {error && <ErrorNotice error={error} onRetry={() => void load()} />}{" "}
      {actionError && <ErrorNotice error={actionError} />}
      {active && (
        <div className="panel">
          <Loading
            label={
              data.processing_step === "QUEUED"
                ? "Analyse en attente de traitement…"
                : "Analyse des documents en cours…"
            }
          />
          <p className="help-text centered">
            Vous pouvez revenir plus tard : le dossier reste enregistré.
          </p>
        </div>
      )}
      {data.status === "FAILED" && (
        <section className="issue-panel">
          <h2>L’analyse a été interrompue</h2>
          <p>
            Vos documents sont conservés. Relancez le traitement ou vérifiez les
            données.
          </p>
          <small>Référence : {data.error_code}</small>
          <div>
            <button
              className="button primary"
              disabled={busy}
              onClick={() =>
                void action(() => analyzeCase(id, data.version, true))
              }
            >
              Réessayer l’analyse
            </button>
          </div>
        </section>
      )}
      {closed && (
        <div className="info-note">
          <CheckCircle2 />
          <p>
            Dossier clôturé. Motif :{" "}
            {
              (
                {
                  EXPORTED: "brouillon exporté",
                  NO_ISSUE: "aucun écart",
                  DISMISSED: "demande écartée",
                  UNSUPPORTED: "cas non pris en charge",
                  ABANDONED: "dossier abandonné",
                } as Record<string, string>
              )[data.close_reason || ""]
            }
            . La clôture ne modifie pas les montants du suivi ci-dessous.
          </p>
        </div>
      )}
      <Issues issues={data.review_issues} />
      {editable && complete && (
        <div className="review-callout">
          <div>
            <h2>
              {data.status === "NEEDS_REVIEW"
                ? "Vérifiez les points signalés"
                : "Contrôlez les informations sources"}
            </h2>
            <p>
              Consultez les originaux et corrigez les valeurs si nécessaire.
            </p>
          </div>
          <Link
            className="button secondary"
            href={`/dossiers/${id}/verification`}
          >
            Vérifier les données <ArrowRight size={17} />
          </Link>
        </div>
      )}
      {eligible && result && (
        <>
          <section className="result-summary">
            <div>
              <span className="eyebrow">
                {data.status === "NO_DISCREPANCY"
                  ? "AUCUN ÉCART DÉTECTÉ"
                  : "AVOIR POTENTIEL HORS TAXES"}
              </span>
              <h2>{money(result.potential_credit_net, result.currency)}</h2>
              <p>
                {data.status === "NO_DISCREPANCY"
                  ? "Les lignes comparées ne présentent aucun écart retenu."
                  : "Un montant à vérifier avec votre fournisseur."}
              </p>
            </div>
            <FileText size={42} />
          </section>
          {result.findings.length > 0 && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Comprendre les écarts</h2>
                  <p>Commande et facture, rapprochées ligne par ligne.</p>
                </div>
              </div>
              <div className="table-scroll">
                <table className="cases-table comparison-table">
                  <thead>
                    <tr>
                      <th>Lignes</th>
                      <th>Quantité commandée / facturée</th>
                      <th>Prix unitaires HT</th>
                      <th>Écart quantité HT</th>
                      <th>Écart prix HT</th>
                      <th>Potentiel HT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.findings.map((f, i) => (
                      <tr key={i}>
                        <td>
                          <strong>
                            BC {f.po_line_number} · FAC {f.invoice_line_number}
                          </strong>
                          <div className="source-links">
                            {(["PO", "INVOICE"] as const).map((role) => {
                              const source =
                                role === "PO" ? f.po_source : f.invoice_source;
                              return (
                                <details key={role}>
                                  <summary>
                                    {role === "PO" ? "Commande" : "Facture"} ·
                                    p. {source.page}
                                  </summary>
                                  <p>
                                    {source.text ||
                                      "Texte source non disponible."}
                                  </p>
                                  <a
                                    target="_blank"
                                    rel="noreferrer"
                                    href={`/api/v1/documents/${data.documents[role]!.id}/content#page=${source.page}`}
                                  >
                                    Voir l’original ↗
                                  </a>
                                </details>
                              );
                            })}
                          </div>
                        </td>
                        <td>
                          {quantity(f.ordered_quantity)} /{" "}
                          {quantity(f.invoiced_quantity)}
                        </td>
                        <td>
                          {money(f.po_unit_price, result.currency)} /{" "}
                          {money(f.invoice_unit_price, result.currency)}
                        </td>
                        <td>
                          {money(f.quantity_component_net, result.currency)}
                        </td>
                        <td>{money(f.price_component_net, result.currency)}</td>
                        <td className="amount">
                          {money(f.potential_credit_net, result.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <p className="limitation">
            Comparaison avec la commande uniquement : les livraisons, retours,
            accords ultérieurs et avoirs déjà émis doivent être vérifiés. Le
            potentiel n’est ni un montant dû confirmé ni une somme récupérée.
          </p>
          {result.warnings.length > 0 && (
            <details className="info-note">
              <summary>Limites complémentaires du contrôle</summary>
              <ul>
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      {data.draft && (
        <DraftEditor
          key={`draft:${data.id}`}
          data={data}
          onSaved={load}
          onDirtyChange={setDraftDirty}
        />
      )}
      {(data.status === "CLAIM_DRAFTED" ||
        data.recovery.entries.length > 0) && (
        <RecoveryTracker
          key={`tracking:${data.id}`}
          data={data}
          onSaved={load}
          draftDirty={draftDirty}
        />
      )}
      <section className="panel documents-panel">
        <div className="panel-heading">
          <h2>Documents du dossier</h2>
          {editable && (
            <button
              className="text-button"
              onClick={() => setReplace(!replace)}
            >
              {replace ? "Masquer l’import" : "Importer ou remplacer"}
            </button>
          )}
        </div>
        <div className="document-links">
          {(["PO", "INVOICE"] as const).map((role) => (
            <div key={role}>
              <FileText size={21} />
              <div>
                <strong>{role === "PO" ? "Bon de commande" : "Facture"}</strong>
                {data.documents[role] ? (
                  <a
                    href={`/api/v1/documents/${data.documents[role]!.id}/content`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {data.documents[role]!.original_name} ↗
                  </a>
                ) : (
                  <p>À importer</p>
                )}
              </div>
            </div>
          ))}
        </div>
        {(replace || !complete) && editable && (
          <div className="panel-body">
            <div className="upload-grid">
              {(["PO", "INVOICE"] as const).map((role) => (
                <UploadSlot
                  key={role}
                  role={role}
                  file={files[role] || null}
                  stored={data.documents[role]?.original_name}
                  disabled={busy}
                  onChange={(file) => setFiles((v) => ({ ...v, [role]: file }))}
                />
              ))}
            </div>
            <p className="help-text">
              Tout remplacement invalide les résultats et le brouillon
              précédents.
            </p>
            <button
              className="button secondary"
              disabled={busy || !Object.keys(files).length}
              onClick={() =>
                void action(async () => {
                  let current: CaseSummary = data;
                  for (const role of ["PO", "INVOICE"] as const) {
                    if (files[role]) {
                      const updated = await uploadFile(
                        current,
                        role,
                        files[role]!,
                      );
                      current = updated;
                      setFiles((v) => {
                        const n = { ...v };
                        delete n[role];
                        return n;
                      });
                    }
                  }
                  setReplace(false);
                })
              }
            >
              Enregistrer les documents
            </button>
          </div>
        )}
      </section>
      {data.status === "PENDING" && !active && complete && (
        <div className="action-bar">
          <p>Les résultats seront calculés après validation des données.</p>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void action(() => analyzeCase(id, data.version))}
          >
            Lancer l’analyse <ArrowRight size={17} />
          </button>
        </div>
      )}
      <div className="case-admin">
        {!closed && (
          <button
            className="text-button"
            disabled={busy || active}
            onClick={() => {
              setConfirmDelete(false);
              dialog.current?.showModal();
            }}
          >
            Clôturer le dossier
          </button>
        )}
        <button
          className="text-button delete-link"
          disabled={busy}
          onClick={() => {
            setConfirmDelete(true);
            dialog.current?.showModal();
          }}
        >
          <Trash2 size={15} /> Supprimer le dossier
        </button>
      </div>
      <dialog ref={dialog} className="confirm-dialog">
        <h2>
          {confirmDelete ? "Supprimer ce dossier ?" : "Clôturer ce dossier ?"}
        </h2>
        <p>
          {confirmDelete
            ? "Les documents, données extraites, brouillons, échanges et preuves d’avoirs seront supprimés du stockage actif. Des copies peuvent subsister dans les sauvegardes selon leur conservation. Cette action est définitive."
            : "La clôture empêche les modifications. Elle ne confirme aucun envoi ou remboursement."}
        </p>
        {!confirmDelete && (
          <label className="field">
            Motif
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="EXPORTED">Brouillon exporté</option>
              <option value="NO_ISSUE">Aucun écart</option>
              <option value="DISMISSED">Demande écartée</option>
              <option value="UNSUPPORTED">Cas non pris en charge</option>
              <option value="ABANDONED">Dossier abandonné</option>
            </select>
          </label>
        )}
        <div className="draft-actions">
          <button
            className="button secondary"
            onClick={() => dialog.current?.close()}
          >
            Annuler
          </button>
          <button
            className={`button ${confirmDelete ? "danger" : "primary"}`}
            disabled={busy}
            onClick={() => {
              dialog.current?.close();
              void action(async () => {
                if (confirmDelete) {
                  await api(`/cases/${id}`, {
                    method: "DELETE",
                    body: JSON.stringify({
                      expected_version: data.version,
                      confirmed: true,
                    }),
                  });
                  router.push("/");
                } else
                  await api(`/cases/${id}/close`, {
                    method: "POST",
                    body: JSON.stringify({
                      expected_version: data.version,
                      close_reason: reason,
                    }),
                  });
              });
            }}
          >
            {confirmDelete
              ? "Supprimer définitivement"
              : "Confirmer la clôture"}
          </button>
        </div>
      </dialog>
    </>
  );
}
