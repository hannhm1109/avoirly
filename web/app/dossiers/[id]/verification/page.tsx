"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import { api, analyzeCase } from "@/lib/api";
import { useCase } from "@/lib/use-case";
import type {
  CaseDetail,
  CaseSummary,
  DocumentData,
  Line,
  Pair,
  Role,
} from "@/lib/types";
import { ErrorNotice, Loading } from "@/components/ui";
import { Issues } from "@/components/issues";
import { DocumentPreview } from "@/components/document-preview";

const value = (text: string) => text.trim() || null;
const decimal = (text: string) => value(text.replace(",", "."));
const emptyLine = (number: number): Line => ({
  line_number: number,
  sku: null,
  description: null,
  quantity: null,
  unit: null,
  unit_price: null,
  tax_rate: null,
  line_total: null,
  source: { page: 1, text: null },
});
function blank(role: Role): DocumentData {
  return {
    document_type: "UNKNOWN",
    document_number: null,
    document_date: null,
    currency: null,
    supplier: { name: null, tax_id: null },
    buyer: { name: null, tax_id: null },
    prices_include_tax: null,
    adjustments_present: null,
    line_items: [emptyLine(1)],
    subtotal: null,
    tax_total: null,
    total: null,
    warnings: [],
    ...(role === "INVOICE"
      ? { due_date: null, purchase_order_reference: null }
      : {}),
  };
}
function initial(data: CaseDetail, role: Role) {
  const ext = data.extractions[role];
  return structuredClone(
    ext?.corrected || (ext?.raw?.document_type ? ext.raw : blank(role)),
  );
}
function Field({
  label,
  text,
  onChange,
  numeric = false,
  type = "text",
}: {
  label: string;
  text: string | null | undefined;
  onChange: (text: string) => void;
  numeric?: boolean;
  type?: string;
}) {
  return (
    <label className="field">
      {label}
      <input
        type={type}
        inputMode={numeric ? "decimal" : undefined}
        value={text || ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
function TriState({
  label,
  current,
  onChange,
}: {
  label: string;
  current: boolean | null;
  onChange: (v: boolean | null) => void;
}) {
  return (
    <label className="field">
      {label}
      <select
        value={current === null ? "unknown" : String(current)}
        onChange={(e) =>
          onChange(
            e.target.value === "unknown" ? null : e.target.value === "true",
          )
        }
      >
        <option value="unknown">À vérifier</option>
        <option value="false">Non</option>
        <option value="true">Oui</option>
      </select>
    </label>
  );
}

function ReviewForm({ data }: { data: CaseDetail }) {
  const router = useRouter(),
    [role, setRole] = useState<Role>("PO"),
    [page, setPage] = useState(1),
    [pair, setPair] = useState<Pair>(() => ({
      purchase_order: initial(data, "PO"),
      invoice: initial(data, "INVOICE"),
    }));
  const [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [saved, setSaved] = useState<CaseSummary | null>(null),
    [dirty, setDirty] = useState(false);
  const key = role === "PO" ? "purchase_order" : "invoice",
    doc = pair[key];
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function update(changes: Partial<DocumentData>) {
    setPair((v) => ({ ...v, [key]: { ...v[key], ...changes } }));
    setDirty(true);
  }
  function updateLine(index: number, changes: Partial<Line>) {
    update({
      line_items: doc.line_items.map((row, i) =>
        i === index ? { ...row, ...changes } : row,
      ),
    });
  }
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      let record = saved;
      if (!record) {
        record = await api<CaseSummary>(`/cases/${data.id}/review`, {
          method: "PUT",
          body: JSON.stringify({
            expected_version: data.version,
            corrected: pair,
            reason,
            confirm_pair: confirmed,
          }),
        });
        setSaved(record);
        setDirty(false);
      }
      await analyzeCase(record.id, record.version);
      router.push(`/dossiers/${data.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back-link" href={`/dossiers/${data.id}`}>
        <ArrowLeft size={16} /> Retour au dossier
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">VÉRIFICATION DES SOURCES</div>
          <h1>Votre regard, ligne par ligne.</h1>
          <p>Corrigez uniquement ce que le document permet de confirmer.</p>
        </div>
      </div>
      <Issues issues={data.review_issues} />
      <div
        className="review-tabs"
        role="tablist"
        aria-label="Document à vérifier"
      >
        {(["PO", "INVOICE"] as const).map((r) => (
          <button
            key={r}
            role="tab"
            aria-selected={role === r}
            className={r === role ? "selected" : ""}
            onClick={() => {
              setRole(r);
              setPage(1);
            }}
          >
            {r === "PO" ? "01 · Bon de commande" : "02 · Facture"}
          </button>
        ))}
      </div>
      <div className="review-layout">
        <aside className="source-pane">
          <div className="source-toolbar">
            <strong>Document original</strong>
            <label>
              Page{" "}
              <input
                aria-label="Page source affichée"
                type="number"
                min={1}
                max={data.documents[role]?.page_count || 1}
                value={page}
                onChange={(e) =>
                  setPage(
                    Math.min(
                      data.documents[role]?.page_count || 1,
                      Math.max(1, Number(e.target.value) || 1),
                    ),
                  )
                }
              />
            </label>
          </div>
          <DocumentPreview data={data} role={role} page={page} />
          <p className="help-text">
            Les données originales restent conservées dans l’historique.
          </p>
          {data.extractions[role]?.raw?.line_items && (
            <details className="original-values">
              <summary>Valeurs extraites à l’origine</summary>
              {data.extractions[role]!.raw.line_items.map((line, i) => (
                <p key={i}>
                  Ligne {line.line_number} ·{" "}
                  {line.description || "Description inconnue"} · Quantité{" "}
                  {line.quantity || "?"} · Prix HT {line.unit_price || "?"} · p.{" "}
                  {line.source.page}
                </p>
              ))}
            </details>
          )}
        </aside>
        <fieldset className="review-fields" disabled={busy || !!saved}>
          <legend className="sr-only">
            Données du document {role === "PO" ? "commande" : "facture"}
          </legend>
          <div className="panel">
            <div className="panel-heading">
              <h2>Informations du document</h2>
            </div>
            <div className="panel-body field-grid">
              <label className="field">
                Type de document
                <select
                  value={doc.document_type}
                  onChange={(e) => update({ document_type: e.target.value })}
                >
                  <option value="UNKNOWN">À vérifier</option>
                  <option value={role === "PO" ? "PURCHASE_ORDER" : "INVOICE"}>
                    {role === "PO" ? "Bon de commande" : "Facture"}
                  </option>
                  {role === "INVOICE" && (
                    <option value="CREDIT_NOTE">Avoir</option>
                  )}
                  <option value="OTHER">Autre</option>
                </select>
              </label>
              <Field
                label="Numéro du document"
                text={doc.document_number}
                onChange={(v) => update({ document_number: value(v) })}
              />
              <Field
                label="Date du document"
                type="date"
                text={doc.document_date}
                onChange={(v) => update({ document_date: value(v) })}
              />
              <Field
                label="Devise (MAD, EUR, USD, GBP)"
                text={doc.currency}
                onChange={(v) => update({ currency: value(v.toUpperCase()) })}
              />
              {role === "INVOICE" && (
                <>
                  <Field
                    label="Référence du bon de commande"
                    text={doc.purchase_order_reference}
                    onChange={(v) =>
                      update({ purchase_order_reference: value(v) })
                    }
                  />
                  <Field
                    label="Date d’échéance"
                    type="date"
                    text={doc.due_date}
                    onChange={(v) => update({ due_date: value(v) })}
                  />
                </>
              )}
              {(["supplier", "buyer"] as const).map((p) => (
                <div className="field-group" key={p}>
                  <Field
                    label={
                      p === "supplier"
                        ? "Nom du fournisseur"
                        : "Nom de l’acheteur"
                    }
                    text={doc[p].name}
                    onChange={(v) =>
                      update({ [p]: { ...doc[p], name: value(v) } })
                    }
                  />
                  <Field
                    label={
                      p === "supplier"
                        ? "Identifiant fiscal fournisseur"
                        : "Identifiant fiscal acheteur"
                    }
                    text={doc[p].tax_id}
                    onChange={(v) =>
                      update({ [p]: { ...doc[p], tax_id: value(v) } })
                    }
                  />
                </div>
              ))}
              <TriState
                label="Prix incluant la TVA ?"
                current={doc.prices_include_tax}
                onChange={(v) => update({ prices_include_tax: v })}
              />
              <TriState
                label="Remises ou frais supplémentaires ?"
                current={doc.adjustments_present}
                onChange={(v) => update({ adjustments_present: v })}
              />
            </div>
          </div>
          <div className="lines-heading">
            <h2>Lignes extraites</h2>
            <span>{doc.line_items.length} / 100</span>
          </div>
          <p className="help-text">
            Laissez les valeurs inconnues vides. Les quantités, prix et totaux
            sont vérifiés sur le serveur.
          </p>
          {doc.line_items.map((line, index) => (
            <section className="panel line-editor" key={index}>
              <div className="panel-heading">
                <h3>Ligne {line.line_number}</h3>
                <button
                  className="text-button delete-link"
                  aria-label={`Supprimer la ligne ${line.line_number}`}
                  onClick={() =>
                    update({
                      line_items: doc.line_items.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <div className="panel-body field-grid">
                <label className="field">
                  Numéro de ligne
                  <input
                    type="number"
                    min={1}
                    value={line.line_number}
                    onChange={(e) =>
                      updateLine(index, { line_number: Number(e.target.value) })
                    }
                  />
                </label>
                <Field
                  label="Référence produit (SKU)"
                  text={line.sku}
                  onChange={(v) => updateLine(index, { sku: value(v) })}
                />
                <div className="full-width">
                  <Field
                    label="Description"
                    text={line.description}
                    onChange={(v) =>
                      updateLine(index, { description: value(v) })
                    }
                  />
                </div>
                <Field
                  label="Quantité"
                  numeric
                  text={line.quantity}
                  onChange={(v) => updateLine(index, { quantity: decimal(v) })}
                />
                <Field
                  label="Unité"
                  text={line.unit}
                  onChange={(v) => updateLine(index, { unit: value(v) })}
                />
                <Field
                  label={`Prix unitaire HT (${doc.currency || "devise à vérifier"})`}
                  numeric
                  text={line.unit_price}
                  onChange={(v) =>
                    updateLine(index, { unit_price: decimal(v) })
                  }
                />
                <Field
                  label="TVA (%)"
                  numeric
                  text={line.tax_rate}
                  onChange={(v) => updateLine(index, { tax_rate: decimal(v) })}
                />
                <Field
                  label={`Total de ligne HT (${doc.currency || "devise à vérifier"})`}
                  numeric
                  text={line.line_total}
                  onChange={(v) =>
                    updateLine(index, { line_total: decimal(v) })
                  }
                />
                <label className="field">
                  Page source
                  <input
                    type="number"
                    min={1}
                    max={data.documents[role]?.page_count || 1}
                    value={line.source.page}
                    onFocus={() => setPage(line.source.page)}
                    onChange={(e) =>
                      updateLine(index, {
                        source: {
                          ...line.source,
                          page: Number(e.target.value),
                        },
                      })
                    }
                  />
                </label>
                <label className="field full-width">
                  Texte source
                  <textarea
                    rows={2}
                    value={line.source.text || ""}
                    onChange={(e) =>
                      updateLine(index, {
                        source: { ...line.source, text: value(e.target.value) },
                      })
                    }
                  />
                </label>
              </div>
            </section>
          ))}
          <button
            className="button secondary"
            disabled={doc.line_items.length >= 100}
            onClick={() =>
              update({
                line_items: [
                  ...doc.line_items,
                  emptyLine(
                    Math.max(0, ...doc.line_items.map((l) => l.line_number)) +
                      1,
                  ),
                ],
              })
            }
          >
            <Plus size={16} /> Ajouter une ligne
          </button>
          <section className="panel totals-editor">
            <div className="panel-heading">
              <h2>
                Totaux du document · {doc.currency || "devise à vérifier"}
              </h2>
            </div>
            <div className="panel-body field-grid">
              <Field
                label="Sous-total hors taxes"
                numeric
                text={doc.subtotal}
                onChange={(v) => update({ subtotal: decimal(v) })}
              />
              <Field
                label="Total TVA"
                numeric
                text={doc.tax_total}
                onChange={(v) => update({ tax_total: decimal(v) })}
              />
              <Field
                label="Total TTC"
                numeric
                text={doc.total}
                onChange={(v) => update({ total: decimal(v) })}
              />
              <label className="field full-width">
                Incertitudes restantes (une par ligne)
                <textarea
                  rows={3}
                  value={doc.warnings.join("\n")}
                  onChange={(e) =>
                    update({
                      warnings: e.target.value
                        ? e.target.value.split("\n")
                        : [],
                    })
                  }
                />
                <small>
                  Ne retirez une incertitude qu’après vérification de la source.
                  Toute incertitude restante bloque le brouillon.
                </small>
              </label>
            </div>
          </section>
        </fieldset>
      </div>
      <section className="panel correction-confirmation">
        <div className="panel-body">
          <h2>Enregistrer votre vérification</h2>
          <p>
            Les références produit et les unités servent à rapprocher les
            lignes. Une ambiguïté bloque toujours le calcul.
          </p>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy || !!saved}
              onChange={(e) => {
                setConfirmed(e.target.checked);
                setDirty(true);
              }}
            />{" "}
            Je confirme que cette facture correspond à ce bon de commande.
            Obligatoire si la référence de commande manque.
          </label>
          <label className="field">
            Motif de la correction ou de la confirmation
            <textarea
              rows={2}
              maxLength={2000}
              disabled={busy || !!saved}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setDirty(true);
              }}
              placeholder="Ex. : quantité vérifiée sur la page 1 de la facture."
            />
          </label>
          {!!error && <ErrorNotice error={error} />}{" "}
          {saved && (
            <p className="success-message">
              Corrections enregistrées. Vous pouvez relancer l’analyse ou
              revenir au dossier.
            </p>
          )}
          <div className="action-bar">
            <p>
              Une nouvelle version sera créée. Le résultat précédent sera
              invalidé.
            </p>
            <button
              className="button primary"
              disabled={busy || !reason.trim()}
              onClick={() => void submit()}
            >
              <Save size={17} />
              {busy
                ? "Enregistrement…"
                : saved
                  ? "Relancer l’analyse"
                  : "Enregistrer et relancer"}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
export default function ReviewPage() {
  const { id } = useParams<{ id: string }>(),
    { data, error, load, active } = useCase(id);
  if (!data)
    return error ? (
      <ErrorNotice error={error} onRetry={() => void load()} />
    ) : (
      <Loading />
    );
  if (
    active ||
    data.status === "CLOSED" ||
    !data.documents.PO ||
    !data.documents.INVOICE
  )
    return (
      <div className="empty-state">
        <h1>Vérification indisponible</h1>
        <p>
          Les deux documents doivent être importés et le dossier doit être
          ouvert, sans analyse en cours.
        </p>
        <Link className="button secondary" href={`/dossiers/${id}`}>
          Retour au dossier
        </Link>
      </div>
    );
  return <ReviewForm key={data.current_revision} data={data} />;
}
