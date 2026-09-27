"use client";
import type { CaseDetail, Role } from "@/lib/types";
export function DocumentPreview({
  data,
  role,
  page = 1,
}: {
  data: CaseDetail;
  role: Role;
  page?: number;
}) {
  const doc = data.documents[role];
  if (!doc) return <p>Document non importé.</p>;
  const url = `/api/v1/documents/${doc.id}/content`;
  return (
    <section className="document-preview">
      <div className="preview-heading">
        <strong>{doc.original_name}</strong>
        <a
          className="text-button"
          target="_blank"
          rel="noreferrer"
          href={`${url}#page=${page}`}
        >
          Ouvrir l’original ↗
        </a>
      </div>
      {doc.mime_type === "application/pdf" ? (
        <iframe
          key={`${doc.id}-${page}`}
          title={`Original ${role === "PO" ? "bon de commande" : "facture"} page ${page}`}
          src={`${url}#page=${page}`}
        />
      ) : (
        <div className="image-preview">
          <img src={url} alt={`Original ${doc.original_name}`} />
        </div>
      )}
    </section>
  );
}
