"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Files, Plus, ShieldCheck } from "lucide-react";
import { SessionStatus } from "./session-status";

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="workspace">
      <a className="skip-link" href="#main">
        Aller au contenu
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="Avoirly, accueil">
          <span className="brand-mark">a</span>avoirly
          <span className="brand-dot">.</span>
        </Link>
        <div className="workspace-label">VOTRE ESPACE DE TRAVAIL</div>
        <nav aria-label="Navigation principale">
          <Link
            href="/"
            className={`nav-item ${pathname !== "/dossiers/nouveau" ? "active" : ""}`}
          >
            <Files size={19} /> Mes dossiers <ArrowUpRight size={15} />
          </Link>
          <Link
            href="/dossiers/nouveau"
            className={`nav-item ${pathname === "/dossiers/nouveau" ? "active" : ""}`}
          >
            <Plus size={19} /> Nouveau dossier
          </Link>
        </nav>
        <div className="sidebar-note">
          <span className="tiny-label">DU DOCUMENT AU BROUILLON</span>
          <p>
            Vos chiffres.
            <br />
            Une vision plus claire.
          </p>
          <ol>
            <li>Importez vos documents</li>
            <li>Vérifiez les écarts</li>
            <li>Préparez votre demande</li>
          </ol>
        </div>
        <footer className="sidebar-footer">
          <ShieldCheck size={19} />
          <span>
            Aucun email envoyé
            <br />
            <small>Vous gardez la main.</small>
          </span>
        </footer>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <span>
            <span className="muted">Espace de travail</span>
            <span className="crumb-slash">/</span>Fournisseurs
          </span>
          <span className="local-label">
            <SessionStatus /> <span className="language">FR</span>
          </span>
        </header>
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <footer className="page-footer">
          <span>Avoirly</span> Spot invoice discrepancies. Simplify supplier
          claims.
          <Link href="/confidentialite" className="privacy-link">
            Confidentialité
          </Link>
        </footer>
      </div>
    </div>
  );
}
