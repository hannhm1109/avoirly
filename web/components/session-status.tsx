"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
export function SessionStatus() {
  const pathname = usePathname(),
    [session, setSession] = useState<{
      mode: string;
      signed_in: boolean;
      email?: string;
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetch("/auth/session", { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((s) => {
        if (active) setSession(s);
      })
      .catch(() => {
        if (active) setError("Session indisponible");
      });
    return () => {
      active = false;
    };
  }, [pathname]);
  if (error) return <span>{error}</span>;
  if (!session) return <span>Connexion…</span>;
  if (session.mode === "local")
    return (
      <>
        <i />
        Version locale
      </>
    );
  if (!session.signed_in) return <a href="/connexion">Se connecter</a>;
  return (
    <>
      <span className="account-email">{session.email}</span>
      <button
        className="text-button"
        onClick={async () => {
          try {
            const r = await fetch("/auth/logout", { method: "POST" });
            if (!r.ok) throw new Error();
            window.location.assign("/connexion");
          } catch {
            setError("Déconnexion indisponible. Réessayez.");
          }
        }}
      >
        Se déconnecter
      </button>
    </>
  );
}
