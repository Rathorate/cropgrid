"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Sprout } from "lucide-react";

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) return "http://localhost:8000";
  return "";
}

export default function AccountPage() {
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("BUYER");

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("role");
    if (requested === "SELLER" || requested === "BUYER") setRole(requested);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    if (!apiBase()) { setError("The API URL is not configured for this site."); setBusy(false); return; }
    const form = new FormData(event.currentTarget);
    const body = registering
      ? { full_name: form.get("full_name"), email: form.get("email"), password: form.get("password"), role }
      : { email: form.get("email"), password: form.get("password") };
    try {
      const response = await fetch(`${apiBase()}/api/v1/auth/${registering ? "register" : "login"}`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Could not sign in. Please try again.");
      window.location.assign("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not connect to CropGrid.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="accountPage">
    <section className="accountCard">
      <Link className="accountBrand" href="/"><span><Sprout size={20}/></span> CropGrid</Link>
      <p className="eyebrow label">CROPGRID MARKETPLACE</p>
      <h1>{registering ? "Create your account" : "Welcome back"}</h1>
      <p className="accountIntro">{registering ? "Join as a buyer or seller to trade agricultural produce." : "Sign in to continue to your CropGrid workspace."}</p>
      <form onSubmit={submit} className="accountForm">
        {registering && <label>Full name<input name="full_name" required minLength={2} maxLength={120} autoComplete="name"/></label>}
        <label>Email<input name="email" type="email" required autoComplete="email"/></label>
        <label>Password<input name="password" type="password" required minLength={registering ? 10 : 1} maxLength={128} autoComplete={registering ? "new-password" : "current-password"}/>{registering && <small>Use at least 10 characters.</small>}</label>
        {registering && <label>Account type<select value={role} onChange={e=>setRole(e.target.value)}><option value="BUYER">Buyer</option><option value="SELLER">Seller</option></select></label>}
        {error && <div className="formerror" role="alert">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? "Please wait…" : registering ? "Create account" : "Sign in"}</button>
      </form>
      <p className="accountSwitch">{registering ? "Already registered?" : "New to CropGrid?"} <button onClick={()=>{setRegistering(v=>!v);setError("")}}>{registering ? "Sign in" : "Create account"}</button></p>
      <p className="accountAdminNote">Admin accounts are created by the system owner and cannot be selected during public registration.</p>
      <Link className="accountBack" href="/">← Return to marketplace</Link>
    </section>
  </main>;
}
