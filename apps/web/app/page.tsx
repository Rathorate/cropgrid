"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Bell, ChevronDown, CircleHelp, Clock3, Download, Filter, LayoutDashboard, Menu, MoreHorizontal, Package, Plus, Search, ShieldCheck, SlidersHorizontal, Sparkles, Sprout, TrendingUp, Truck, Wallet, X, Mic } from "lucide-react";

type Listing = { id: number; crop_name: string; quantity_tons: number; moisture_percentage: number; location_state: string; asking_price_per_ton_ngn: number; quality_grade: string; is_export_ready: boolean; supplier_name: string; description: string };
const initial: Listing[] = [
  { id: 1, crop_name: "Ginger", quantity_tons: 120, moisture_percentage: 8.2, location_state: "Kaduna", asking_price_per_ton_ngn: 1850000, quality_grade: "GRADE_A", is_export_ready: true, supplier_name: "Northern Harvest Co.", description: "Cleaned and sun-dried. Ready for export." },
  { id: 2, crop_name: "Cashew nuts", quantity_tons: 85, moisture_percentage: 7.4, location_state: "Kogi", asking_price_per_ton_ngn: 2420000, quality_grade: "GRADE_A", is_export_ready: true, supplier_name: "Greenfield Aggregators", description: "Raw cashew nuts with consistent kernel outturn." },
  { id: 3, crop_name: "Sesame seed", quantity_tons: 240, moisture_percentage: 6.8, location_state: "Niger", asking_price_per_ton_ngn: 1960000, quality_grade: "GRADE_B", is_export_ready: true, supplier_name: "Savanna Produce Ltd.", description: "Natural white sesame, cleaned and bagged." },
  { id: 4, crop_name: "Cocoa beans", quantity_tons: 64, moisture_percentage: 7.1, location_state: "Ondo", asking_price_per_ton_ngn: 3180000, quality_grade: "GRADE_A", is_export_ready: false, supplier_name: "Oke-Ogun Farmers Union", description: "Fermented, dried cocoa beans from this season." },
  { id: 5, crop_name: "Soybeans", quantity_tons: 310, moisture_percentage: 9.5, location_state: "Benue", asking_price_per_ton_ngn: 875000, quality_grade: "GRADE_B", is_export_ready: false, supplier_name: "Benue Grain Partners", description: "Yellow soybeans, bulk supply available." },
  { id: 6, crop_name: "Hibiscus flower", quantity_tons: 48, moisture_percentage: 8.0, location_state: "Kano", asking_price_per_ton_ngn: 1320000, quality_grade: "GRADE_A", is_export_ready: true, supplier_name: "Arewa Botanicals", description: "Deep red dried hibiscus calyces, export packed." },
];
const currency = (n: number) => `₦${new Intl.NumberFormat("en-NG", { maximumFractionDigits: 0 }).format(n)}`;
const icons: Record<string,string> = { Ginger:"🫚", "Cashew nuts":"🥜", "Sesame seed":"🌾", "Cocoa beans":"🍫", Soybeans:"🫘", "Hibiscus flower":"🌺", Maize:"🌽", "Palm oil":"🫙", Cassava:"🥔" };
function getApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window === "undefined" || ["localhost", "127.0.0.1"].includes(window.location.hostname)) return "http://localhost:8000";
  return "";
}
const categoryCrops: Record<string, string[]> = {
  Grains: ["maize", "soybean", "sorghum", "millet", "rice"],
  "Nuts & seeds": ["cashew", "sesame", "groundnut"],
  Spices: ["ginger", "hibiscus", "pepper"],
  "Cash crops": ["cocoa", "palm", "cassava"],
};

export default function Home() {
  const [listings, setListings] = useState(initial);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState("All commodities");
  const [modal, setModal] = useState(false);
  const [toast, setToast] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [checkoutListing, setCheckoutListing] = useState<Listing | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [checkoutForm, setCheckoutForm] = useState({ buyer_name: "", buyer_email: "", quantity_tons: "1" });
  const audioRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({ crop_name:"", quantity_tons:"", location_state:"", asking_price_per_ton_ngn:"", moisture_percentage:"", is_export_ready:false });
  const [apiOnline, setApiOnline] = useState(false);
  const [apiChecked, setApiChecked] = useState(false);
  const [apiError, setApiError] = useState("");
  const [today, setToday] = useState("");
  useEffect(() => {
    setToday(new Intl.DateTimeFormat("en-NG", { weekday: "long", month: "long", day: "numeric" }).format(new Date()).toUpperCase());
    const api = getApiBase();
    if (!api) { setApiChecked(true); setApiOnline(false); return; }
    Promise.all([
      fetch(`${api}/api/v1/health`),
      fetch(`${api}/api/v1/inventories`),
    ]).then(async ([health, inventory]) => {
      setApiOnline(health.ok);
      if (!health.ok) throw new Error("The API health check failed.");
      if (!inventory.ok) throw new Error("Could not load marketplace listings.");
      const rows = await inventory.json();
      if (Array.isArray(rows)) setListings(rows);
    }).catch(() => setApiOnline(false)).finally(() => setApiChecked(true));
  }, []);
  const filtered = useMemo(() => listings.filter(l => (active === "All commodities" || (categoryCrops[active] || [active.toLowerCase()]).some(crop => l.crop_name.toLowerCase().includes(crop))) && `${l.crop_name} ${l.location_state} ${l.supplier_name}`.toLowerCase().includes(query.toLowerCase())), [listings, query, active]);
  const availableTons = listings.reduce((total, listing) => total + listing.quantity_tons, 0);
  const commodityCount = new Set(listings.map(listing => listing.crop_name.toLowerCase())).size;
  function notify(s: string) { setToast(s); setTimeout(() => setToast(""), 3000); }
  async function publish(e: React.FormEvent) {
    e.preventDefault();
    setApiError("");
    const payload = { supplier_name:"CropGrid Supplier", quality_grade:"GRADE_B", description:"New supplier listing.", ...form, quantity_tons:Number(form.quantity_tons), asking_price_per_ton_ngn:Number(form.asking_price_per_ton_ngn), moisture_percentage:Number(form.moisture_percentage || 0) };
    try {
      const api = getApiBase();
      if (!api) throw new Error("API URL is missing. Set NEXT_PUBLIC_API_URL in the frontend deployment settings and redeploy.");
      const res = await fetch(`${api}/api/v1/inventories`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
      const result = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The API could not save this listing.");
      setListings(v => [result, ...v]);
      setModal(false);
      setForm({ crop_name:"", quantity_tons:"", location_state:"", asking_price_per_ton_ngn:"", moisture_percentage:"", is_export_ready:false });
      notify("Listing saved to the marketplace.");
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Could not save listing. Check the API connection and try again.");
    }
  }
  async function parseVoice(file?: File) {
    if (!file) return;
    const body = new FormData(); body.append("file", file);
    setParsing(true);
    try {
      const api = getApiBase();
      if (!api) throw new Error("API URL is missing. Set NEXT_PUBLIC_API_URL in the frontend deployment settings and redeploy.");
      const response = await fetch(`${api}/api/v1/ai/parse-audio`, { method:"POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Voice parsing is unavailable.");
      const draft = result.draft || {};
      setForm(current => ({ ...current, crop_name:draft.crop_name || current.crop_name, quantity_tons:draft.quantity_tons == null ? current.quantity_tons : String(draft.quantity_tons), location_state:draft.location_state || current.location_state, asking_price_per_ton_ngn:draft.asking_price_per_ton_ngn == null ? current.asking_price_per_ton_ngn : String(draft.asking_price_per_ton_ngn), moisture_percentage:draft.moisture_percentage == null ? current.moisture_percentage : String(draft.moisture_percentage) }));
      notify("Voice draft filled. Review every field before publishing.");
    } catch (error) { notify(error instanceof Error ? error.message : "Voice parsing is unavailable."); }
    finally { setParsing(false); if (audioRef.current) audioRef.current.value = ""; }
  }
  async function beginCheckout(e: React.FormEvent) {
    e.preventDefault();
    if (!checkoutListing) return;
    setCheckoutBusy(true);
    setCheckoutError("");
    try {
      const api = getApiBase();
      if (!api) throw new Error("API URL is missing. Set NEXT_PUBLIC_API_URL in the frontend settings.");
      const response = await fetch(`${api}/api/v1/payments/initialize`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ inventory_id: checkoutListing.id, quantity_tons: Number(checkoutForm.quantity_tons), buyer_name: checkoutForm.buyer_name, buyer_email: checkoutForm.buyer_email, currency: "NGN" }) });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Could not start checkout.");
      if (typeof result.authorization_url !== "string" || !result.authorization_url.startsWith("https://checkout.paystack.com/")) throw new Error("The payment provider returned an invalid checkout link.");
      window.location.assign(result.authorization_url);
    } catch (error) {
      setCheckoutError(error instanceof Error ? error.message : "Could not start checkout. Please try again.");
      setCheckoutBusy(false);
    }
  }
  return <main className="shell">
    <aside className={`sidebar ${drawer ? "open" : ""}`}>
      <div className="brand"><div className="brandmark"><Sprout size={22}/></div><span>cropgrid</span><button className="closeNav" onClick={() => setDrawer(false)}><X size={19}/></button></div>
      <div className="workspace"><div className="avatar avatar-dark">CG</div><div><strong>CropGrid workspace</strong><small>Free plan</small></div><ChevronDown size={15} className="subtle"/></div>
      <div className="navgroup"><div className="navlabel">WORKSPACE</div><button className="navitem selected"><LayoutDashboard size={18}/> Overview</button><button className="navitem" onClick={() => document.getElementById("marketplace")?.scrollIntoView({behavior:"smooth"})}><Package size={18}/> Marketplace <span className="navbadge">6</span></button><button className="navitem" onClick={() => notify("Your order pipeline is clear.")}><Truck size={18}/> Orders</button><button className="navitem" onClick={() => notify("Wallet preview — no funds are held in this demo.")}><Wallet size={18}/> Wallet</button></div>
      <div className="navgroup"><div className="navlabel">TOOLS</div><button className="navitem" onClick={() => notify("AI listing assistant is ready for a voice integration.")}><Sparkles size={18}/> AI assistant <span className="ai-pill">BETA</span></button><button className="navitem" onClick={() => notify("Export documents are drafts until official integrations are configured.")}><Download size={18}/> Export documents</button></div>
      <div className="sidebottom"><div className="helpbox"><div className="helpicon"><CircleHelp size={18}/></div><b>Need a hand?</b><p>Our team is here to help your trade grow.</p><button onClick={() => notify("Support contact: hello@cropgrid.ng")}>Visit help center <ArrowRight size={14}/></button></div><div className="profile"><div className="avatar avatar-green">AO</div><div><b>Amara Okafor</b><small>Supplier account</small></div><MoreHorizontal size={19} className="subtle"/></div></div>
    </aside>
    {drawer && <div className="scrim" onClick={() => setDrawer(false)}/>}
    <section className="main">
      <header className="topbar"><button className="mobileMenu" onClick={() => setDrawer(true)}><Menu/></button><div className="crumb">Workspace <span>/</span> <b>Overview</b></div><div className="topright"><div className="api-status"><i className={apiOnline ? "online" : "offline"}/>{apiOnline ? "API connected" : apiChecked ? "API unavailable" : "Connecting…"}</div><button className="iconbtn" aria-label="Help" onClick={() => notify("CropGrid support is here for you.")}><CircleHelp size={19}/></button><button className="iconbtn notification" aria-label="Notifications" onClick={() => notify("You’re all caught up.")}><Bell size={19}/><i/></button><div className="topavatar">AO</div></div></header>
      <div className="content"><div className="welcome"><div><div className="eyebrow"><span className="pulse"/> {today || "CROPGRID MARKETPLACE"}</div><h1>Good morning, Amara <span>🌤️</span></h1><p>Sample workspace data. Orders and prices below are illustrative only.</p></div><button className="primary" onClick={() => { setApiError(""); setModal(true); }}><Plus size={18}/> Add a listing</button></div>
        <div className="statgrid"><article className="statcard"><div className="stathead"><span>Marketplace listings</span><span className="staticon green"><Package size={18}/></span></div><div className="statvalue">{listings.length}</div><div className="statfoot">Across <b>{commodityCount} commodities</b></div></article><article className="statcard"><div className="stathead"><span>Available stock</span><span className="staticon yellow"><Sprout size={18}/></span></div><div className="statvalue">{new Intl.NumberFormat("en-NG", { maximumFractionDigits: 1 }).format(availableTons)} <small>tons</small></div><div className="statfoot"><span className="dot greenDot"/> Total listed quantity</div></article><article className="statcard"><div className="stathead"><span>Orders</span><span className="staticon blue"><Truck size={18}/></span></div><div className="statvalue">Demo</div><div className="statfoot">Sample orders below · no real payment</div></article><article className="statcard"><div className="stathead"><span>Market prices</span><span className="staticon purple"><TrendingUp size={18}/></span></div><div className="statvalue">Sample</div><div className="statfoot">Illustrative chart · no live feed</div></article></div>
        <div className="banner"><div className="bannericon"><ShieldCheck size={21}/></div><div className="bannertext"><b>Trade with confidence</b><span>Verify your supplier profile to unlock buyer trust badges and larger contracts.</span></div><button onClick={() => notify("Profile verification will be available when identity checks are configured.")}>Complete verification <ArrowRight size={15}/></button><button className="bannerclose" aria-label="Dismiss" onClick={(e) => (e.currentTarget.parentElement as HTMLElement).remove()}><X size={17}/></button></div>
        <div className="sectionhead" id="marketplace"><div><div className="eyebrow label">DISCOVER & TRADE</div><h2>Marketplace</h2><p>Seasonal inventory from suppliers across West Africa.</p></div><button className="outline" onClick={() => notify("Showing all current listings.")}><SlidersHorizontal size={16}/> Browse all</button></div>
        <div className="markettools"><div className="tabs">{["All commodities","Grains","Nuts & seeds","Spices","Cash crops"].map(t=><button key={t} onClick={() => setActive(t)} className={active===t ? "tab active" : "tab"}>{t}</button>)}</div><label className="searchbox"><Search size={17}/><input aria-label="Search crops and locations" placeholder="Search crops, locations..." value={query} onChange={e=>setQuery(e.target.value)}/><kbd>⌘ K</kbd></label><button className="filterBtn" onClick={() => {setActive("All commodities");setQuery("");}}><Filter size={16}/><span>Clear filters</span></button></div>
        <div className="listinggrid">{filtered.map((l,i)=><article className="listing" key={l.id}><div className={`cropimage crop${i%6}`}><div className="cropemoji">{icons[l.crop_name]||"🌿"}</div><div className="imageTop"><span className="fresh"><i/> Supplier listing</span><button aria-label="Save listing" onClick={e=>{e.currentTarget.classList.toggle("saved");notify("Saved listing updated.")}}>♡</button></div><span className="quality"><span className={l.quality_grade==="GRADE_A"?"gradeA":"gradeB"}/> {l.quality_grade.replace("GRADE_","Grade ")}</span></div><div className="listingbody"><div className="cropname"><h3>{l.crop_name}</h3>{l.is_export_ready&&<span title="Supplier marked export ready"><ShieldCheck size={15}/></span>}</div><div className="supplier"><div className="miniavatar">{l.supplier_name.slice(0,1)}</div><span>{l.supplier_name}</span></div><div className="listingmeta"><span><b>{l.quantity_tons} tons</b> available</span><span>·</span><span>{l.location_state}</span></div><div className="specs"><span><small>MOISTURE</small><b>{l.moisture_percentage}%</b></span><span className="specDivider"/><span><small>GRADE</small><b>{l.quality_grade.replace("GRADE_", "")} <i>●</i></b></span><span className="specDivider"/><span><small>ORIGIN</small><b>{l.location_state}</b></span></div><div className="listingfoot"><div><small>Asking price / ton</small><b>{currency(l.asking_price_per_ton_ngn)}</b></div><button className="buyButton" aria-label={`Buy ${l.crop_name}`} onClick={() => { setCheckoutError(""); setCheckoutForm({buyer_name:"", buyer_email:"", quantity_tons:"1"}); setCheckoutListing(l); }}>Buy</button></div></div></article>)}</div>
        {!filtered.length && <div className="empty"><Package size={26}/><b>No listings found</b><span>Try another crop or location.</span></div>}
        <div className="lowergrid"><article className="panel orderpanel"><div className="panelhead"><div><h3>Sample orders</h3><p>Illustrative only · orders are not connected to the API</p></div><button className="textlink" onClick={() => notify("Order management is a future feature; these are sample rows.")}>About orders <ArrowRight size={14}/></button></div><div className="orderrow"><div className="orderpic">🫚</div><div className="orderdesc"><b>Ginger · 12 tons</b><span>To Meridian Foods, Lagos</span></div><span className="status transit"><Truck size={13}/> In transit</span><span className="orderprice">₦22.2m</span><button className="dots" aria-label="Order options"><MoreHorizontal size={18}/></button></div><div className="orderrow"><div className="orderpic">🥜</div><div className="orderdesc"><b>Cashew nuts · 8 tons</b><span>To Atlas Global, Rotterdam</span></div><span className="status review"><Clock3 size={13}/> In review</span><span className="orderprice">₦19.4m</span><button className="dots" aria-label="Order options"><MoreHorizontal size={18}/></button></div><div className="orderrow"><div className="orderpic">🌾</div><div className="orderdesc"><b>Sesame seed · 20 tons</b><span>To Kano Foods, Kano</span></div><span className="status delivered"><ArrowDownLeft size={13}/> Delivered</span><span className="orderprice">₦39.2m</span><button className="dots" aria-label="Order options"><MoreHorizontal size={18}/></button></div></article><article className="panel insight"><div className="insighthead"><span className="insighticon"><Sparkles size={17}/></span><span>MARKET PULSE</span><span className="live sample"><i/> SAMPLE</span></div><h3>Prices are moving<br/>in your favor.</h3><p>Sample price data shows how a regional market signal could appear here. No live price feed is connected.</p><div className="chart"><div className="chartlabels"><span>₦1.9m</span><span>₦1.8m</span><span>₦1.7m</span></div><svg viewBox="0 0 420 80" preserveAspectRatio="none" aria-label="Illustrative market price trend"><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#91c98e" stopOpacity=".27"/><stop offset="100%" stopColor="#91c98e" stopOpacity="0"/></linearGradient></defs><path d="M0 65 C30 63 32 48 62 52 S95 42 119 49 S157 28 184 40 S220 55 246 33 S282 46 311 24 S352 36 376 17 S402 22 420 6 V80 H0Z" fill="url(#fill)"/><path d="M0 65 C30 63 32 48 62 52 S95 42 119 49 S157 28 184 40 S220 55 246 33 S282 46 311 24 S352 36 376 17 S402 22 420 6" fill="none" stroke="#468e55" strokeWidth="2.5"/></svg></div><div className="insightfoot"><span>ILLUSTRATIVE MARKET SIGNAL</span><button onClick={() => notify("Market rates are illustrative. Connect trusted price feeds before making trade decisions.")}>Explore prices <ArrowRight size={14}/></button></div></article></div>
        <footer><span>© 2026 CropGrid Technologies</span><span><i className={apiOnline?"online":"offline"}/> {apiOnline?"All systems operational":"Local preview is active"}</span><span>Built for trade that grows <span className="heart">♥</span></span></footer>
      </div>
    </section>
    {modal && <div className="modalback" onClick={e=>{if(e.target===e.currentTarget)setModal(false)}}><form className="modal" onSubmit={publish}><div className="modalhead"><div><div className="eyebrow label">SELL ON CROPGRID</div><h2>Add a listing</h2><p>Share your crop with buyers across the region.</p></div><div className="modalheadActions"><button type="button" className="voiceButton" disabled={parsing} onClick={()=>audioRef.current?.click()}><Mic size={14}/>{parsing ? "Parsing…" : "Voice draft"}</button><input ref={audioRef} className="visuallyHidden" type="file" accept="audio/*" onChange={e=>parseVoice(e.target.files?.[0])}/><button type="button" className="iconbtn" onClick={()=>setModal(false)}><X size={20}/></button></div></div>{apiError && <div className="formerror" role="alert">{apiError}</div>}<label>Commodity<select required value={form.crop_name} onChange={e=>setForm({...form,crop_name:e.target.value})}><option value="">Select a commodity</option>{["Ginger","Cashew nuts","Sesame seed","Cocoa beans","Soybeans","Hibiscus flower","Maize","Palm oil","Cassava"].map(x=><option key={x}>{x}</option>)}</select></label><div className="formrow"><label>Quantity (tons)<input required min="0.1" step="0.1" type="number" placeholder="e.g. 25" value={form.quantity_tons} onChange={e=>setForm({...form,quantity_tons:e.target.value})}/></label><label>Location<input required placeholder="State, Nigeria" value={form.location_state} onChange={e=>setForm({...form,location_state:e.target.value})}/></label></div><div className="formrow"><label>Price per ton (₦)<input required min="1" type="number" placeholder="e.g. 1850000" value={form.asking_price_per_ton_ngn} onChange={e=>setForm({...form,asking_price_per_ton_ngn:e.target.value})}/></label><label>Moisture (%)<input min="0" max="100" type="number" step="0.1" placeholder="Optional" value={form.moisture_percentage} onChange={e=>setForm({...form,moisture_percentage:e.target.value})}/></label></div><label className="checkbox"><input type="checkbox" checked={form.is_export_ready} onChange={e=>setForm({...form,is_export_ready:e.target.checked})}/> This batch is export ready</label><div className="modnote"><Sparkles size={16}/> AI quality grading is not enabled. Grade and specs should be independently verified.</div><div className="modalactions"><button type="button" className="outline" onClick={()=>setModal(false)}>Cancel</button><button className="primary"><Plus size={17}/> Publish listing</button></div></form></div>}
    {toast&&<div className="toast"><div><ShieldCheck size={18}/></div>{toast}<button onClick={()=>setToast("")}><X size={15}/></button></div>}
  </main>;
}
