"use client";
import { useState } from "react";
import { Copy, Download, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { CaseDetail, CaseSummary } from "@/lib/types";
import { ErrorNotice } from "./ui";
export function DraftEditor({
  data,
  onSaved,
  onDirtyChange,
}: {
  data: CaseDetail;
  onSaved: () => Promise<unknown>;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [subject, setSubject] = useState(data.draft!.subject),
    [body, setBody] = useState(data.draft!.body),
    [version, setVersion] = useState(data.version),
    [saved, setSaved] = useState({
      subject: data.draft!.subject,
      body: data.draft!.body,
    });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [message, setMessage] = useState("");
  async function act(action: "save" | "copy" | "download") {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      if (subject !== saved.subject || body !== saved.body) {
        const result = await api<CaseSummary>(`/cases/${data.id}/draft`, {
          method: "PATCH",
          body: JSON.stringify({ expected_version: version, subject, body }),
        });
        setVersion(result.version);
        setSaved({ subject, body });
        await onSaved();
        onDirtyChange?.(false);
      }
      const text = `Objet : ${subject}\n\n${body}\n`;
      if (action === "copy") await navigator.clipboard.writeText(text);
      if (action === "download") {
        const url = URL.createObjectURL(
          new Blob([text], { type: "text/plain;charset=utf-8" }),
        );
        const a = document.createElement("a");
        a.href = url;
        a.download = `avoirly-${data.id.slice(0, 8)}.txt`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      setMessage(
        action === "copy"
          ? "Brouillon copié."
          : action === "download"
            ? "Brouillon téléchargé."
            : "Brouillon enregistré.",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel draft-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">À RELIRE AVANT ENVOI</div>
          <h2>Votre brouillon de demande</h2>
          <p>Modifiez le texte, puis copiez-le dans votre messagerie.</p>
        </div>
        <span className="badge neutral">Non envoyé</span>
      </div>
      <div className="panel-body">
        <label className="field">
          Objet
          <input
            value={subject}
            maxLength={500}
            onChange={(e) => {
              setSubject(e.target.value);
              onDirtyChange?.(
                e.target.value !== saved.subject || body !== saved.body,
              );
            }}
          />
        </label>
        <label className="field">
          Message
          <textarea
            aria-label="Message"
            className="draft-body"
            value={body}
            maxLength={20000}
            onChange={(e) => {
              setBody(e.target.value);
              onDirtyChange?.(
                subject !== saved.subject || e.target.value !== saved.body,
              );
            }}
          />
        </label>
        {!!error && <ErrorNotice error={error} />}
        <div className="draft-actions">
          <button
            className="button secondary"
            disabled={busy || !subject.trim() || !body.trim()}
            onClick={() => void act("save")}
          >
            <Save size={17} /> Enregistrer
          </button>
          <button
            className="button secondary"
            disabled={busy || !subject.trim() || !body.trim()}
            onClick={() => void act("download")}
          >
            <Download size={17} /> Télécharger
          </button>
          <button
            className="button primary"
            disabled={busy || !subject.trim() || !body.trim()}
            onClick={() => void act("copy")}
          >
            <Copy size={17} /> Copier le brouillon
          </button>
        </div>
        <p className="success-message" role="status">
          {message}
        </p>
        <p className="help-text">
          Les modifications sont enregistrées avant la copie ou le
          téléchargement. Un export ne confirme aucun envoi ni avoir reçu.
        </p>
      </div>
    </section>
  );
}
