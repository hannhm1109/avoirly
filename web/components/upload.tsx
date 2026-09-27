"use client";
import { useState } from "react";
import { FileUp, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import type { CaseSummary, Role } from "@/lib/types";
import { ErrorNotice } from "./ui";

export function UploadSlot({
  role,
  file,
  onChange,
  disabled = false,
  stored,
}: {
  role: Role;
  file: File | null;
  onChange: (file: File) => void;
  disabled?: boolean;
  stored?: string;
}) {
  const [error, setError] = useState<unknown>(null);
  function choose(value?: File) {
    if (!value) return;
    setError(null);
    if (!value.size || value.size > 10 * 1024 * 1024) {
      setError(new Error("Choisissez un document non vide de 10 Mo maximum."));
      return;
    }
    if (!/\.(pdf|png|jpe?g)$/i.test(value.name)) {
      setError(new Error("Formats acceptés : PDF, PNG et JPEG."));
      return;
    }
    onChange(value);
  }
  return (
    <section className="upload-card">
      <h2>
        <span className="step-number">{role === "PO" ? "01" : "02"}</span>
        {role === "PO" ? "Bon de commande" : "Facture"}
      </h2>
      <label
        className={`dropzone ${file || stored ? "selected" : ""}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!disabled) choose(e.dataTransfer.files[0]);
        }}
      >
        {file || stored ? <CheckCircle2 size={32} /> : <FileUp size={32} />}
        <strong>{file?.name || stored || "Glissez votre document ici"}</strong>
        <span>
          {file || stored
            ? "Choisir un autre fichier"
            : "ou cliquez pour le sélectionner"}
        </span>
        <input
          aria-label={
            role === "PO" ? "Document bon de commande" : "Document facture"
          }
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          disabled={disabled}
          onChange={(e) => choose(e.target.files?.[0])}
        />
        <small>PDF, PNG, JPEG · 10 Mo maximum</small>
      </label>
      {!!error && <ErrorNotice error={error} />}
    </section>
  );
}
export async function uploadFile(record: CaseSummary, role: Role, file: File) {
  const body = new FormData();
  body.set("role", role);
  body.set("expected_version", String(record.version));
  body.set("file", file);
  return api<CaseSummary>(`/cases/${record.id}/documents`, {
    method: "POST",
    body,
  });
}
