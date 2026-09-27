"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, ShieldCheck } from "lucide-react";
import { createCase, analyzeCase } from "@/lib/api";
import type { CaseSummary, Role } from "@/lib/types";
import { UploadSlot, uploadFile } from "@/components/upload";
import { ErrorNotice } from "@/components/ui";

export default function NewCase() {
  const router = useRouter(),
    record = useRef<CaseSummary | null>(null),
    uploaded = useRef<Partial<Record<Role, File>>>({});
  const [files, setFiles] = useState<Partial<Record<Role, File>>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [step, setStep] = useState("");
  async function submit() {
    if (busy || !files.PO || !files.INVOICE) return;
    setBusy(true);
    setError(null);
    try {
      if (!record.current) record.current = await createCase();
      for (const role of ["PO", "INVOICE"] as const) {
        const file = files[role]!;
        if (uploaded.current[role] === file) continue;
        setStep(
          role === "PO"
            ? "Import du bon de commande…"
            : "Import de la facture…",
        );
        record.current = await uploadFile(record.current, role, file);
        uploaded.current[role] = file;
      }
      setStep("Lancement de l’analyse…");
      await analyzeCase(record.current.id, record.current.version);
      router.push(`/dossiers/${record.current.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      setStep("");
    }
  }
  return (
    <>
      <Link className="back-link" href="/">
        <ArrowLeft size={16} /> Mes dossiers
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">NOUVEAU DOSSIER</div>
          <h1>Deux documents. Une vue claire.</h1>
          <p>Associez un bon de commande à la facture correspondante.</p>
        </div>
      </div>
      <div className="upload-grid">
        {(["PO", "INVOICE"] as const).map((role) => (
          <UploadSlot
            key={role}
            role={role}
            file={files[role] || null}
            onChange={(file) => setFiles((v) => ({ ...v, [role]: file }))}
            disabled={busy}
          />
        ))}
      </div>
      <div className="info-note">
        <ShieldCheck size={22} />
        <p>
          Documents conservés sur cet ordinateur. Lors d’une extraction
          automatique, leur contenu est transmis à OpenAI. PDF : 10 pages
          maximum. Images : 25 mégapixels maximum.
        </p>
      </div>
      {error && <ErrorNotice error={error} />}
      {error && record.current && (
        <Link className="text-button" href={`/dossiers/${record.current.id}`}>
          Ouvrir le dossier enregistré →
        </Link>
      )}
      <div className="action-bar">
        <p>Aucun e-mail n’est envoyé automatiquement.</p>
        <button
          className="button primary"
          disabled={busy || !files.PO || !files.INVOICE}
          onClick={() => void submit()}
        >
          {busy ? step : "Analyser les documents"}
          <ArrowRight size={18} />
        </button>
      </div>
    </>
  );
}
