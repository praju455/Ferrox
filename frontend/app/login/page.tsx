"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getApiBase, getToken, login, setApiBase } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [apiBase, updateApiBase] = useState("http://127.0.0.1:8000/api/v1");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    updateApiBase(getApiBase());
    if (getToken()) router.replace("/workspace");
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setApiBase(apiBase);
    try {
      await login(email, password);
      router.push("/workspace");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <Link className="brand" href="/">
          <span className="brand-mark">F/</span><span className="brand-word">Ferrox</span>
        </Link>
        <div>
          <span className="section-index light">CATALOG OPERATIONS</span>
          <h1>Source evidence in. Trusted product records out.</h1>
          <p>Sign in to ingest technical sources, inspect field lineage, resolve conflicts, and release catalog-ready data.</p>
        </div>
        <small>Gemini primary / Groq fallback / OpenAI fallback</small>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <form onSubmit={submit}>
          <span className="section-index">SECURE ACCESS</span>
          <h2 id="login-title">Sign in to Ferrox</h2>
          <p>Use the reviewer or administrator account created by your catalog team.</p>
          <label>
            <span>Email</span>
            <input autoComplete="username" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label>
            <span>Password</span>
            <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          <label>
            <span>API address</span>
            <input onChange={(event) => updateApiBase(event.target.value)} required value={apiBase} />
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="solid-command" disabled={busy} type="submit">
            {busy ? "Signing in..." : "Sign in"}<span aria-hidden="true">&#8594;</span>
          </button>
          <Link className="login-back" href="/">Back to overview</Link>
        </form>
      </section>
    </main>
  );
}
