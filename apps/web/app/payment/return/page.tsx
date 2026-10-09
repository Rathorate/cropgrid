"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, LoaderCircle, ShieldCheck } from "lucide-react";

type Verification = { reference: string; status: string; currency: string; amount: string; message: string };

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (["localhost", "127.0.0.1"].includes(window.location.hostname)) return "http://localhost:8000";
  return "";
}

export default function PaymentReturn() {
  const [attempt, setAttempt] = useState(0);
  const [payment, setPayment] = useState<Verification | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function verify() {
      const reference = new URLSearchParams(window.location.search).get("reference");
      if (!reference) { setError("No payment reference was returned. Check your email or contact CropGrid support."); setLoading(false); return; }
      const api = apiBase();
      if (!api) { setError("Payment verification is not configured for this site."); setLoading(false); return; }
      setLoading(true); setError("");
      try {
        const response = await fetch(`${api}/api/v1/payments/verify/${encodeURIComponent(reference)}`, { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Payment verification failed.");
        if (!cancelled) setPayment(result);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Payment verification failed.");
      } finally { if (!cancelled) setLoading(false); }
    }
    verify();
    return () => { cancelled = true; };
  }, [attempt]);

  const paid = payment?.status === "SUCCESS";
  const review = payment?.status === "PAID_REVIEW";
  return <main className="paymentResult"><div className="paymentCard"><div className={`paymentIcon ${paid ? "success" : review ? "warning" : ""}`}>{loading ? <LoaderCircle className="spin" size={26}/> : <ShieldCheck size={26}/>}</div><p className="eyebrow label">CROPGRID PAYMENT</p><h1>{loading ? "Verifying payment…" : paid ? "Payment confirmed" : review ? "Payment needs attention" : payment?.status === "PENDING" ? "Payment is processing" : error ? "Could not verify payment" : "Payment not completed"}</h1><p>{loading ? "We are checking the transaction directly with Paystack." : review ? "The provider confirmed payment, but inventory needs manual review. Please contact support before retrying." : payment?.message || error || "The payment was not confirmed. You can return to the marketplace."}</p>{payment && <div className="paymentDetails"><span>Reference</span><code>{payment.reference}</code><span>Amount</span><b>{payment.currency} {payment.amount}</b></div>}{error && <div className="formerror" role="alert">{error}</div>}<div className="paymentActions"><Link className="outline" href="/"><ArrowLeft size={16}/> Marketplace</Link>{payment?.status === "PENDING" && <button className="primary" onClick={()=>setAttempt(v=>v+1)}>Check again</button>}</div><small>Do not share card details or your payment password with anyone.</small></div></main>;
}
