"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

type Answer = { answer: string; mode: string; sources: { id: string; title: string }[]; notice: string; needs_human: boolean };
type Ticket = { id: number; question: string; status: string; reply: string; user_id?: number };

export default function SupportAssistant({ api, signedIn, admin }: { api: string; signedIn: boolean; admin: boolean }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function request(path: string, options: RequestInit = {}) {
    const response = await fetch(`${api}/api/v1${path}`, { ...options, credentials: "include" });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Help is unavailable. Check your connection and use the FAQ below.");
    return result;
  }
  async function refresh() { setTickets(await request(admin ? "/admin/support-tickets" : "/support/tickets")); }
  useEffect(() => { if (signedIn) refresh().catch(err => setError(err.message)); }, [signedIn, api, admin]); // eslint-disable-line react-hooks/exhaustive-deps
  async function ask(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setAnswer(null);
    try { setAnswer(await request("/support/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not load help."); }
    finally { setBusy(false); }
  }
  async function leaveRequest() {
    setBusy(true); setError("");
    try { await request("/support/tickets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save the request."); }
    finally { setBusy(false); }
  }
  return <section className="supportAssistant" aria-label="CropGrid help assistant"><h3>Help assistant</h3><p>Get guidance while support is away. Account changes, payment decisions and disputes require authorized review. Never enter passwords, card details, OTPs or API keys.</p>
    {signedIn ? <><form onSubmit={ask}><label htmlFor="support-question">What do you need help with?</label><textarea id="support-question" minLength={3} maxLength={2000} rows={3} value={question} onChange={e => setQuestion(e.target.value)} placeholder="For example: How do I upload a video?" required /><div className="supportActions"><button className="primary" disabled={busy || question.trim().length < 3}>{busy ? "Working…" : "Get help"}</button><button type="button" className="outline" disabled={busy || question.trim().length < 3} onClick={leaveRequest}>Leave a support request</button></div></form>
      {error && <div className="formerror" role="alert">{error}</div>}{answer && <article className="supportAnswer" aria-live="polite"><b>{answer.mode === "ai" ? "AI guidance" : "Reviewed help article"}</b><p>{answer.answer}</p><small>{answer.notice}</small><p>Reference: {answer.sources.map(source => source.title).join(", ")}</p>{answer.needs_human && <p>If this does not solve the issue, leave a support request for review.</p>}</article>}
      <div className="supportActions"><h3>{admin ? "Support review queue" : "Your support requests"}</h3><button type="button" className="outline" onClick={() => refresh().catch(err => setError(err.message))}>Refresh requests</button></div><p>Requests are saved for human review. There is no guaranteed response time.</p>{tickets.length ? tickets.map(ticket => <article className="supportTicket" key={ticket.id}><b>#{ticket.id} · {ticket.status}</b><p>{ticket.question}</p>{ticket.reply && <p><strong>Support reply:</strong> {ticket.reply}</p>}{admin && <TicketEditor ticket={ticket} onSave={async (status, reply) => { await request(`/admin/support-tickets/${ticket.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status, reply }) }); await refresh(); }}/>}</article>) : <p>No support requests yet.</p>}
    </> : <p><Link className="signInLink" href="/account">Sign in for guided help and private support requests</Link>. You can read the FAQ below without signing in.</p>}
  </section>;
}

function TicketEditor({ ticket, onSave }: { ticket: Ticket; onSave: (status: string, reply: string) => Promise<void> }) {
  const [reply, setReply] = useState(ticket.reply);
  const [status, setStatus] = useState(ticket.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try { await onSave(status, reply); } catch (err) { setError(err instanceof Error ? err.message : "Could not save."); } finally { setBusy(false); } }}><label>Reply to request #{ticket.id}<textarea value={reply} maxLength={2000} onChange={e => setReply(e.target.value)} /></label><label>Status<select value={status} onChange={e => setStatus(e.target.value)}>{["OPEN", "REVIEWING", "RESOLVED"].map(value => <option key={value}>{value}</option>)}</select></label><button className="outline" disabled={busy || (status === "RESOLVED" && !reply.trim())}>{busy ? "Saving…" : "Save support reply"}</button>{error && <div className="formerror" role="alert">{error}</div>}</form>;
}
