"use client";

import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { useCaseTool } from "@/lib/use-case-tool";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  FileCheck2,
  Files,
  Plus,
  ScanLine,
} from "lucide-react";
import { getCases } from "@/lib/api";
import { dateLabel, money } from "@/lib/format";
import type { CasePage } from "@/lib/types";
import { Badge, ErrorNotice, Loading } from "@/components/ui";

export default function CasesPage() {
  const [data, setData] = useState<CasePage | null>(null),
    [error, setError] = useState<unknown>(null),
    [offset, setOffset] = useState(0);
  const load = useCallback(async () => {
    try {
      setError(null);
      const updated = await getCases(offset);
      flushSync(() => setData(updated));
      return updated;
    } catch (e) {
      setError(e);
      return null;
    }
  }, [offset]);
  useCaseTool(load);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (
      !data?.items.some(
        (c) => c.status === "PROCESSING" || c.processing_step === "QUEUED",
      )
    )
      return;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [data, load]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">RAPPROCHEMENT FOURNISSEURS</div>
          <h1>Vos dossiers, en clair.</h1>
          <p>Repérez les écarts. Préparez des demandes documentées.</p>
        </div>
        <Link className="button primary" href="/dossiers/nouveau">
          <Plus size={18} /> Nouveau dossier
        </Link>
      </div>
      {error ? (
        <ErrorNotice error={error} onRetry={() => void load()} />
      ) : !data ? (
        <Loading label="Chargement des dossiers…" />
      ) : (
        <>
          <div className="metric-grid">
            <div className="metric">
              <span className="metric-icon">
                <Files size={20} />
              </span>
              <span>Dossiers affichés</span>
              <strong>{data.items.length.toString().padStart(2, "0")}</strong>
              <small>Sur cette page</small>
            </div>
            <div className="metric">
              <span className="metric-icon amber-icon">
                <ScanLine size={20} />
              </span>
              <span>À vérifier</span>
              <strong>
                {data.items
                  .filter((c) => c.status === "NEEDS_REVIEW")
                  .length.toString()
                  .padStart(2, "0")}
              </strong>
              <small>Votre regard fait la différence</small>
            </div>
            <div className="metric featured">
              <span className="metric-icon">
                <CheckCheck size={20} />
              </span>
              <span>Avoir potentiel hors taxes</span>
              <div className="money-stack">
                {Object.entries(data.potential_credit_by_currency || {})
                  .length ? (
                  Object.entries(data.potential_credit_by_currency).map(
                    ([currency, amount]) => (
                      <strong key={currency}>{money(amount, currency)}</strong>
                    ),
                  )
                ) : (
                  <strong>—</strong>
                )}
              </div>
              <small>Écarts vérifiés sur cette page · à confirmer</small>
            </div>
          </div>
          {data.items.some((c) => c.recovery?.has_sent_record) && (
            <section
              className="panel dashboard-tracking"
              aria-label="Totaux du suivi"
            >
              <div className="panel-heading">
                <div>
                  <h2>Demandes et avoirs enregistrés</h2>
                  <p>Sur cette page · hors taxes · suivi manuel</p>
                </div>
              </div>
              <div className="panel-body recovery-metrics">
                {(
                  [
                    ["sent", "Demandé"],
                    ["promised", "Promis"],
                    ["confirmed", "Reçu et vérifié"],
                  ] as const
                ).map(([kind, label]) => (
                  <div className="recovery-total" key={kind}>
                    <span>{label} HT</span>
                    {Object.entries(data.recovery_by_currency[kind]).map(
                      ([currency, value]) => (
                        <strong key={currency}>{money(value, currency)}</strong>
                      ),
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
          <section className="panel cases-panel">
            <div className="panel-heading">
              <div>
                <h2>
                  Mes dossiers{" "}
                  <span className="count">{data.items.length}</span>
                </h2>
                <p>Du premier document au suivi des avoirs.</p>
              </div>
              <span className="tiny-label">MIS À JOUR RÉCEMMENT</span>
            </div>
            {data.items.length ? (
              <div className="table-scroll">
                <table className="cases-table">
                  <thead>
                    <tr>
                      <th>Fournisseur & facture</th>
                      <th>Statut</th>
                      <th>Avoir potentiel HT</th>
                      <th>Avoir confirmé HT</th>
                      <th>Mis à jour</th>
                      <th>
                        <span className="sr-only">Ouvrir</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link
                            className="case-title"
                            href={`/dossiers/${c.id}`}
                          >
                            <span className="file-tile">
                              <FileCheck2 size={21} />
                            </span>
                            <span>
                              <strong>
                                {c.supplier_name || "Documents à vérifier"}
                              </strong>
                              <small>
                                {c.invoice_number ||
                                  `Dossier ${c.id.slice(0, 8)}`}
                                {c.po_number ? ` · ${c.po_number}` : ""}
                              </small>
                            </span>
                          </Link>
                        </td>
                        <td>
                          <Badge status={c.status} />
                        </td>
                        <td className="amount">
                          {[
                            "DISCREPANCY_FOUND",
                            "CLAIM_DRAFTED",
                            "NO_DISCREPANCY",
                            "CLAIM_SENT",
                            "AWAITING_RESPONSE",
                            "CREDIT_PROMISED",
                            "CREDIT_CONFIRMED",
                          ].includes(c.status)
                            ? money(c.potential_credit_net, c.currency)
                            : "—"}
                        </td>
                        <td className="amount">
                          {c.recovery?.has_sent_record
                            ? money(
                                c.recovery.confirmed_net,
                                c.recovery.currency,
                              )
                            : "—"}
                        </td>
                        <td className="muted">{dateLabel(c.updated_at)}</td>
                        <td>
                          <Link
                            className="icon-button"
                            aria-label={`Ouvrir ${c.invoice_number || "le dossier"}`}
                            href={`/dossiers/${c.id}`}
                          >
                            <ArrowUpRight size={19} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <span className="empty-icon">
                  <Files size={35} />
                </span>
                <h3>Votre premier rapprochement commence ici.</h3>
                <p>
                  Réunissez un bon de commande et sa facture.
                  <br />
                  Avoirly vous aide à comparer les deux, ligne par ligne.
                </p>
                <Link className="button primary" href="/dossiers/nouveau">
                  Comparer mes documents <ArrowRight size={17} />
                </Link>
                <span className="format-note">
                  PDF, PNG ou JPEG · 10 Mo par document
                </span>
              </div>
            )}
            <div className="table-footer">
              <span>Les montants restent séparés par devise.</span>
              <div className="pagination">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - 20))}
                >
                  Précédent
                </button>
                <span>Page {offset / 20 + 1}</span>
                <button
                  disabled={data.items.length < 20}
                  onClick={() => setOffset((v) => v + 20)}
                >
                  Suivant
                </button>
              </div>
            </div>
          </section>
          <div className="trust-note">
            <FileCheck2 size={21} />
            <p>
              <strong>Des écarts à vérifier, des demandes à relire.</strong> Un
              montant potentiel ne confirme ni la livraison ni un avoir dû. Vous
              validez chaque étape.
            </p>
          </div>
        </>
      )}
    </>
  );
}
