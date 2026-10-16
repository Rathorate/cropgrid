"use client";

import { useEffect, useState } from "react";

export type ListingMedia = { id: number; kind: "image" | "video"; url: string };
export type DeliveryOrder = { reference: string; status: string; delivery_status?: string; tracking_details?: string; dispute_reason?: string; can_dispatch?: boolean; can_confirm_receipt?: boolean };

async function apiRequest(api: string, path: string, options: RequestInit = {}) {
  const response = await fetch(`${api}/api/v1${path}`, { ...options, credentials: "include" });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The request could not be completed.");
  return result;
}

export function ListingGallery({ api, crop, media = [] }: { api: string; crop: string; media?: ListingMedia[] }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  if (!media.length) return null;
  const current = media[Math.min(selected, media.length - 1)];
  return <div className="listingMedia">
    <button type="button" onClick={() => setOpen(true)} aria-label={`View photos and videos of ${crop}`}>
      {media[0].kind === "image" ? <img src={`${api}${media[0].url}`} alt={`${crop} supplied by the seller`} loading="lazy" /> : <video src={`${api}${media[0].url}`} muted preload="metadata" />}
      <span>View {media.length} photo{media.length > 1 ? "s" : ""} / video{media.length > 1 ? "s" : ""}</span>
    </button>
    {open && <div className="modalback" onClick={e => { if (e.target === e.currentTarget) setOpen(false); }}><section className="modal mediaViewer" role="dialog" aria-modal="true" aria-label={`${crop} media`}><div className="modalhead"><h2>{crop}</h2><button type="button" className="outline" onClick={() => setOpen(false)}>Close</button></div>
      {current.kind === "image" ? <img src={`${api}${current.url}`} alt={`${crop}, photo ${selected + 1}`} /> : <video key={current.id} src={`${api}${current.url}`} controls playsInline preload="metadata" />}
      <div className="mediaNavigation">{media.map((item, index) => <button type="button" className={selected === index ? "primary" : "outline"} key={item.id} onClick={() => setSelected(index)}>{item.kind === "image" ? "Photo" : "Video"} {index + 1}</button>)}</div>
      <p>Seller supplied media. Check the produce and delivery terms with the seller before checkout.</p>
    </section></div>}
  </div>;
}

export function MediaPicker({ files, onChange, disabled }: { files: File[]; onChange: (files: File[]) => void; disabled: boolean }) {
  const [previews, setPreviews] = useState<string[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { const urls = files.map(file => URL.createObjectURL(file)); setPreviews(urls); return () => urls.forEach(url => URL.revokeObjectURL(url)); }, [files]);
  function choose(selected: FileList | null) {
    if (!selected) return;
    const next = [...files, ...Array.from(selected)];
    if (next.length > 6) { setError("Choose at most six photos and videos."); return; }
    for (const file of next) {
      if (!["image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"].includes(file.type)) { setError("Choose JPEG, PNG, WebP, MP4 or WebM. Convert other formats first."); return; }
      if (file.size > (file.type.startsWith("image/") ? 8_000_000 : 30_000_000)) { setError("Each photo must be under 8 MB and each video under 30 MB."); return; }
    }
    setError(""); onChange(next);
  }
  return <div className="mediaPicker"><label>Photos and videos<input type="file" multiple disabled={disabled} accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" onChange={e => { choose(e.target.files); e.target.value = ""; }} /></label><p>Up to 6 files: JPEG, PNG or WebP photos (8 MB each), MP4 or WebM videos (30 MB each).</p>{error && <div className="formerror" role="alert">{error}</div>}<div className="mediaPreviews">{files.map((file, index) => <figure key={`${file.name}-${index}`}>{file.type.startsWith("image/") ? <img src={previews[index]} alt={`Selected photo ${index + 1}`} /> : <video src={previews[index]} muted preload="metadata" />}<figcaption>{file.name}</figcaption><button type="button" disabled={disabled} className="outline" onClick={() => onChange(files.filter((_, i) => i !== index))}>Remove</button></figure>)}</div></div>;
}

type Thread = { id: number; crop_name: string; buyer_name: string; seller_name: string };
type Message = { id: number; body: string; mine: boolean; sender_name: string; created_at: string };

export function Messenger({ api, inventoryId, onClose }: { api: string; inventoryId: number | null; onClose: () => void }) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    (async () => {
      const created = inventoryId ? await apiRequest(api, "/conversations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ inventory_id: inventoryId }) }) : null;
      const rows = await apiRequest(api, "/conversations");
      if (active) { setThreads(rows); setSelected(created?.id || rows[0]?.id || null); }
    })().catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [api, inventoryId]);
  useEffect(() => {
    setMessages([]); setBody("");
    if (!selected) return;
    let cursor = 0, inFlight = false;
    const controller = new AbortController();
    async function poll() {
      if (inFlight) return;
      inFlight = true;
      try {
        const rows: Message[] = await apiRequest(api, `/conversations/${selected}/messages?after_id=${cursor}`, { signal: controller.signal });
        if (!controller.signal.aborted && rows.length) { cursor = rows[rows.length - 1].id; setMessages(previous => [...previous, ...rows]); }
      } catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Could not load messages."); }
      finally { inFlight = false; }
    }
    poll(); const timer = setInterval(poll, 4000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [api, selected]);
  async function send(e: React.FormEvent) {
    e.preventDefault(); if (!selected || !body.trim()) return;
    setBusy(true); setError("");
    try { await apiRequest(api, `/conversations/${selected}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body: body.trim() }) }); setBody(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Message was not sent."); }
    finally { setBusy(false); }
  }
  return <div className="modalback"><section className="modal messagesModal" role="dialog" aria-modal="true" aria-label="Buyer and seller messages"><div className="modalhead"><div><h2>Messages</h2><p>Agree on produce, delivery and inspection details. Support administrators can review conversations.</p></div><button className="outline" onClick={onClose}>Close</button></div>{error && <div className="formerror" role="alert">{error}</div>}
    {threads.length ? <><label>Conversation<select value={selected || ""} onChange={e => setSelected(Number(e.target.value))}>{threads.map(thread => <option key={thread.id} value={thread.id}>{thread.crop_name} · {thread.buyer_name} / {thread.seller_name}</option>)}</select></label><div className="messageList" role="log" aria-live="polite">{messages.length ? messages.map(message => <article key={message.id} className={message.mine ? "chatMessage mine" : "chatMessage"}><b>{message.sender_name}</b><p>{message.body}</p><small>{new Date(message.created_at).toLocaleString()}</small></article>) : <p>No messages yet. Start the conversation.</p>}</div><form onSubmit={send}><label htmlFor="chat-body">Your message</label><textarea id="chat-body" value={body} maxLength={2000} onChange={e => setBody(e.target.value)} required /><button className="primary" disabled={busy || !body.trim()}>{busy ? "Sending…" : "Send message"}</button></form></> : <p>No conversations yet. Buyers can use Chat with seller on a listing to start one.</p>}
  </section></div>;
}

export function DeliveryControls({ api, order, onUpdated }: { api: string; order: DeliveryOrder; onUpdated: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function update(action: string) {
    let details = "";
    if (action === "CONFIRM_RECEIPT") { if (!window.confirm("Have you received and inspected this produce? Confirm only after checking your delivery.")) return; }
    else { const answer = window.prompt(action === "DISPATCH" ? "Enter delivery or tracking details:" : "Describe the delivery problem:"); if (!answer?.trim()) return; details = answer; }
    setBusy(true); setError("");
    try { await apiRequest(api, `/orders/${order.reference}/delivery`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, details }) }); onUpdated(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not update delivery."); }
    finally { setBusy(false); }
  }
  if (order.status !== "SUCCESS") return null;
  return <div className="deliveryControls"><b>Delivery: {(order.delivery_status || "AWAITING_DISPATCH").replaceAll("_", " ")}</b>{order.tracking_details && <p>{order.tracking_details}</p>}{order.dispute_reason && <p>Dispute: {order.dispute_reason}</p>}<small>Payment recorded by Paystack. Escrow holding and seller fund release are not enabled.</small><div>{order.can_dispatch && order.delivery_status === "AWAITING_DISPATCH" && <button className="outline" disabled={busy} onClick={() => update("DISPATCH")}>Mark dispatched</button>}{order.can_confirm_receipt && order.delivery_status === "DISPATCHED" && <button className="primary" disabled={busy} onClick={() => update("CONFIRM_RECEIPT")}>Confirm received</button>}{["AWAITING_DISPATCH", "DISPATCHED"].includes(order.delivery_status || "") && <button className="outline" disabled={busy} onClick={() => update("DISPUTE")}>Report delivery problem</button>}</div>{error && <div className="formerror" role="alert">{error}</div>}</div>;
}
