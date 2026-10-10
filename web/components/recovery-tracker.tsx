"use client";

import { useState } from "react";
import { api, trackingAction } from "@/lib/api";
import { dateLabel, money } from "@/lib/format";
import type { CaseDetail, RecoveryEntry } from "@/lib/types";
import { ErrorNotice } from "./ui";

const labels = {
  SENT: "Envoi externe déclaré",
  NOTE: "Réponse fournisseur",
  PROMISE: "Avoir promis",
  CREDIT: "Avoir reçu et vérifié",
};

export function RecoveryTracker({
  data,
  onSaved,
  draftDirty,
}: {
  data: CaseDetail;
  onSaved: () => Promise<unknown>;
  draftDirty: boolean;
}) {
  const r = data.recovery;
  const [kind, setKind] = useState<"note" | "promise" | "credit">("note");
  const [occurred, setOccurred] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [recipient, setRecipient] = useState("");
  const [sentAmount, setSentAmount] = useState(data.potential_credit_net || "");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [verified, setVerified] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [evidenceId, setEvidenceId] = useState("");
  const [voidTarget, setVoidTarget] = useState<RecoveryEntry | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [message, setMessage] = useState("");
  const closed = data.status === "CLOSED";
  const today = new Date().toISOString().slice(0, 10);
  async function act(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      await fn();
      await onSaved();
      setMessage(success);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file) return;
    if (
      !file.size ||
      file.size > 10 * 1024 * 1024 ||
      !/\.(pdf|png|jpe?g)$/i.test(file.name)
    )
      throw new Error(
        "Choisissez un PDF, PNG ou JPEG non vide, de 10 Mo maximum.",
      );
    const body = new FormData();
    body.set("expected_version", String(data.version));
    body.set("file", file);
    const result = await api<{ evidence_id: string }>(
      `/cases/${data.id}/evidence`,
      { method: "POST", body },
    );
    setEvidenceId(result.evidence_id);
    setVerified(false);
    setFile(null);
  }
  if (data.status !== "CLAIM_DRAFTED" && !r.entries.length) return null;
  return (
    <section className="panel recovery-panel" aria-label="Suivi de la demande">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">APRÈS VOTRE ENVOI</div>
          <h2>Suivi de la demande</h2>
          <p>Consignez vos échanges et les avoirs reçus, avec leurs preuves.</p>
        </div>
        <span className="badge neutral">Suivi manuel</span>
      </div>
      <div className="panel-body">
        <div className="recovery-metrics">
          {(
            [
              ["Demandé HT", r.sent_net],
              ["Promis HT", r.promised_net],
              ["Confirmé HT", r.confirmed_net],
            ] as const
          ).map(([label, value]) => (
            <div className="recovery-total" key={label}>
              <span>{label}</span>
              <strong>{money(value, r.currency)}</strong>
            </div>
          ))}
        </div>
        {r.has_sent_record && (
          <p className="help-text">
            Reste de la demande sans avoir confirmé :{" "}
            <strong>{money(r.remaining_claim_net, r.currency)}</strong>.{" "}
            {r.fully_credited
              ? "La demande est intégralement couverte par les preuves enregistrées."
              : "Un avoir partiel ne clôture pas la demande."}{" "}
            Les promesses ne s’ajoutent pas aux avoirs confirmés. Un avoir reçu
            ne prouve pas un remboursement en espèces.
          </p>
        )}
        {!!error && <ErrorNotice error={error} />}
        <p className="success-message" role="status">
          {message}
        </p>
        {!closed && !r.has_sent_record && data.draft && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                () =>
                  trackingAction(data.id, "sent", {
                    expected_version: data.version,
                    draft_id: data.draft!.id,
                    occurred_on: occurred,
                    recipient,
                    amount_net: sentAmount.replace(",", "."),
                    currency: data.currency,
                    sent_outside_app: true,
                  }),
                "Envoi externe enregistré. Aucun message n’a été envoyé par Avoirly.",
              );
            }}
          >
            <h3>Déclarer l’envoi externe</h3>
            <p className="help-text">
              Enregistrez et relisez le brouillon ci-dessus. Confirmez que vous
              avez envoyé cette version depuis votre messagerie. L’envoi sera
              conservé avec son montant et son texte.
            </p>
            <div className="field-grid">
              <label className="field">
                Date d’envoi
                <input
                  type="date"
                  required
                  max={today}
                  value={occurred}
                  onChange={(e) => setOccurred(e.target.value)}
                />
              </label>
              <label className="field">
                Destinataire
                <input
                  required
                  maxLength={320}
                  value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}
                />
              </label>
              <label className="field">
                Montant demandé HT ({data.currency})
                <input
                  required
                  inputMode="decimal"
                  pattern="[0-9]+([.,][0-9]{1,2})?"
                  value={sentAmount}
                  onChange={(e) => setSentAmount(e.target.value)}
                />
              </label>
            </div>
            <label className="tracking-check">
              <input type="checkbox" required disabled={busy} />
              J’ai envoyé ce brouillon enregistré en dehors d’Avoirly.
            </label>
            {draftDirty && (
              <p className="help-text">
                Enregistrez les modifications du brouillon avant de déclarer son
                envoi.
              </p>
            )}
            <button className="button primary" disabled={busy || draftDirty}>
              Enregistrer l’envoi externe
            </button>
          </form>
        )}
        {!closed && r.has_sent_record && (
          <>
            {data.status === "CLAIM_SENT" && (
              <button
                className="button secondary"
                disabled={busy}
                onClick={() =>
                  void act(
                    () =>
                      trackingAction(data.id, "await", {
                        expected_version: data.version,
                      }),
                    "Demande en attente de réponse.",
                  )
                }
              >
                Marquer en attente de réponse
              </button>
            )}
            <form
              className="tracking-form"
              onSubmit={(e) => {
                e.preventDefault();
                const payload = {
                  expected_version: data.version,
                  occurred_on: occurred,
                  note,
                  ...(kind !== "note"
                    ? {
                        amount_net: amount.replace(",", "."),
                        currency: data.currency,
                        reference,
                      }
                    : {}),
                  ...(kind === "promise" ? { due_on: due || null } : {}),
                  ...(kind === "credit"
                    ? { evidence_id: evidenceId, received_and_verified: true }
                    : {}),
                };
                void act(async () => {
                  await trackingAction(data.id, kind, payload);
                  setNote("");
                  setReference("");
                  setAmount("");
                  setVerified(false);
                }, "Suivi enregistré.");
              }}
            >
              <h3>Ajouter au suivi</h3>
              <div className="field-grid">
                <label className="field">
                  Type de suivi
                  <select
                    value={kind}
                    onChange={(e) => {
                      setKind(e.target.value as typeof kind);
                      setVerified(false);
                    }}
                  >
                    <option value="note">Réponse ou note</option>
                    <option value="promise">Promesse d’avoir</option>
                    <option value="credit">Avoir reçu et vérifié</option>
                  </select>
                </label>
                <label className="field">
                  Date du suivi
                  <input
                    type="date"
                    required
                    max={today}
                    value={occurred}
                    onChange={(e) => setOccurred(e.target.value)}
                  />
                </label>
              </div>
              {kind !== "note" && (
                <div className="field-grid">
                  <label className="field">
                    Montant HT ({data.currency})
                    <input
                      required
                      inputMode="decimal"
                      pattern="[0-9]+([.,][0-9]{1,2})?"
                      value={amount}
                      onChange={(e) => {
                        setAmount(e.target.value);
                        setVerified(false);
                      }}
                    />
                  </label>
                  <label className="field">
                    {kind === "credit"
                      ? "Référence de l’avoir reçu"
                      : "Référence de la promesse"}
                    <input
                      required
                      maxLength={200}
                      value={reference}
                      onChange={(e) => {
                        setReference(e.target.value);
                        setVerified(false);
                      }}
                    />
                  </label>
                  {kind === "promise" && (
                    <label className="field">
                      Échéance annoncée
                      <input
                        type="date"
                        min={occurred}
                        value={due}
                        onChange={(e) => setDue(e.target.value)}
                      />
                    </label>
                  )}
                </div>
              )}
              <label className="field">
                Note du suivi
                <textarea
                  required
                  maxLength={4000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Consignez la réponse et expliquez le montant hors taxes."
                />
              </label>
              {kind === "credit" && (
                <div className="credit-proof">
                  <h4>Preuve privée de l’avoir reçu</h4>
                  <p className="help-text">
                    Importez l’avoir reçu ou un justificatif PDF, PNG ou JPEG
                    (10 Mo, 10 pages maximum). Ouvrez-le et vérifiez la facture,
                    le fournisseur, la référence, la devise et le montant HT.
                    Avoirly ne vérifie pas automatiquement ces éléments.
                  </p>
                  <label className="field">
                    Fichier justificatif
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      disabled={busy}
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                  </label>
                  <button
                    type="button"
                    className="button secondary"
                    disabled={busy || !file}
                    onClick={() =>
                      void act(
                        upload,
                        "Justificatif importé. Ouvrez-le avant de confirmer.",
                      )
                    }
                  >
                    Importer le justificatif
                  </button>
                  <label className="field">
                    Justificatif de cet avoir
                    <select
                      required
                      value={evidenceId}
                      onChange={(e) => {
                        setEvidenceId(e.target.value);
                        setVerified(false);
                      }}
                    >
                      <option value="">Choisir un justificatif</option>
                      {r.evidence.map((proof) => (
                        <option key={proof.id} value={proof.id}>
                          {proof.original_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {evidenceId && (
                    <a
                      href={`/api/v1/evidence/${evidenceId}/content`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ouvrir le justificatif ↗
                    </a>
                  )}
                  <label className="tracking-check">
                    <input
                      type="checkbox"
                      required
                      checked={verified}
                      disabled={busy}
                      onChange={(e) => setVerified(e.target.checked)}
                    />
                    J’ai reçu cet avoir et vérifié sa preuve, sa devise et son
                    montant hors taxes.
                  </label>
                </div>
              )}
              <button
                className="button primary"
                disabled={
                  busy || (kind === "credit" && (!evidenceId || !verified))
                }
              >
                {kind === "credit"
                  ? "Confirmer cet avoir reçu"
                  : "Enregistrer le suivi"}
              </button>
            </form>
          </>
        )}
        {r.entries.length > 0 && (
          <div className="tracking-history">
            <h3>Historique conservé</h3>
            <ol>
              {r.entries.map((entry) => (
                <li
                  key={entry.id}
                  className={entry.voided_at ? "voided-entry" : ""}
                >
                  <div className="tracking-entry-heading">
                    <strong>
                      {labels[entry.kind]}
                      {entry.voided_at ? " · annulé" : ""}
                    </strong>
                    <span>{dateLabel(`${entry.occurred_on}T12:00:00Z`)}</span>
                  </div>
                  {entry.amount_net && (
                    <p>
                      <strong>
                        {money(entry.amount_net, entry.currency)} HT
                      </strong>{" "}
                      · {entry.reference}
                    </p>
                  )}
                  <p className="tracking-note">{entry.note}</p>
                  {entry.due_on && (
                    <p>Échéance : {dateLabel(`${entry.due_on}T12:00:00Z`)}</p>
                  )}
                  {entry.evidence_id && (
                    <a
                      target="_blank"
                      rel="noreferrer"
                      href={`/api/v1/evidence/${entry.evidence_id}/content`}
                    >
                      Voir la preuve de cet avoir ↗
                    </a>
                  )}
                  {entry.kind === "SENT" && (
                    <details>
                      <summary>
                        Version déclarée envoyée · {entry.reference}
                      </summary>
                      <strong>{entry.snapshot.subject}</strong>
                      <pre>{entry.snapshot.body}</pre>
                    </details>
                  )}
                  {entry.voided_at ? (
                    <p>Motif d’annulation : {entry.void_reason}</p>
                  ) : (
                    !closed &&
                    entry.revision === data.current_revision && (
                      <button
                        type="button"
                        className="text-button"
                        disabled={busy}
                        onClick={() => {
                          setVoidTarget(entry);
                          setVoidReason("");
                        }}
                      >
                        Corriger cette entrée
                      </button>
                    )
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
        {voidTarget && !closed && (
          <form
            className="tracking-correction"
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                await trackingAction(data.id, `${voidTarget.id}/void`, {
                  expected_version: data.version,
                  reason: voidReason,
                });
                setVoidTarget(null);
              }, "Entrée annulée ; son historique et sa preuve restent conservés.");
            }}
          >
            <h3>Annuler l’entrée « {labels[voidTarget.kind]} »</h3>
            <p>
              L’original reste visible. Ajoutez ensuite une entrée corrigée. Les
              totaux excluent les entrées annulées.
            </p>
            <label className="field">
              Motif de la correction
              <input
                required
                maxLength={2000}
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
              />
            </label>
            <div className="draft-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setVoidTarget(null)}
              >
                Conserver l’entrée
              </button>
              <button className="button danger" disabled={busy}>
                Confirmer l’annulation de l’entrée
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
