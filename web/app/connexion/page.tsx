"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function Login() {
  const router = useRouter(),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "Connexion impossible.");
      setPassword("");
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-container">
      <div className="eyebrow">PILOTE PRIVÉ AVOIRLY</div>
      <h1>Retrouvez vos dossiers.</h1>
      <p>Connectez-vous avec le compte fourni pour le pilote.</p>
      <form className="panel panel-body" onSubmit={submit}>
        <label className="field">
          Adresse e-mail
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            maxLength={320}
          />
        </label>
        <label className="field">
          Mot de passe
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            maxLength={1024}
          />
        </label>
        {error && (
          <p className="error-notice" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>
        <p className="help-text">
          Accès sur invitation. Pour obtenir un compte ou réinitialiser votre
          accès, contactez la personne qui vous a invité.
        </p>
      </form>
      <button
        className="text-button"
        onClick={() => router.push("/confidentialite")}
      >
        Confidentialité et traitement des documents →
      </button>
    </div>
  );
}
