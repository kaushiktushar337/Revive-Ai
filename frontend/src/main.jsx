import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const API = window.REVIVE_API || 'http://127.0.0.1:8000/api';
const AUTH_KEY = 'revive_auth_token';
const panel = 'surface-panel';
const input = 'field-input';
const btn = 'action-btn';
const primary = 'primary-btn';

const money = n => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(n) || 0);
const pct = n => `${Math.round((Number(n) || 0) * 100)}%`;
const pretty = s => String(s || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const isTerminal = e => e.recovered || ['RECOVERED', 'CANCELLED', 'EXPIRED', 'LINK_CANCELLED', 'LINK_EXPIRED', 'NO_ACTION'].includes(String(e.lifecycle_status || '').toUpperCase());

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem(AUTH_KEY);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let response;
  try {
    response = await fetch(`${API}${path}`, { ...options, headers });
  } catch {
    throw new Error(`Cannot reach Revive backend at ${API}. Start FastAPI on port 8000.`);
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    localStorage.removeItem(AUTH_KEY);
    throw new Error('Your session expired. Please log in again.');
  }
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

function App() {
  const [merchant, setMerchant] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [view, setView] = useState('overview');
  const [data, setData] = useState({ metrics: {}, events: [], audit: [] });
  const [toast, setToast] = useState('');

  const refresh = useCallback(async () => {
    const [dashboard, profile, auditRes] = await Promise.all([
      api('/dashboard'),
      api('/auth/me'),
      api('/audit?limit=30'),
    ]);
    setMerchant(profile);
    setData({ ...dashboard, audit: auditRes.logs || [] });
  }, []);

  useEffect(() => {
    (async () => {
      const token = localStorage.getItem(AUTH_KEY);
      if (!token) { setAuthChecking(false); return; }
      try { await refresh(); }
      catch { localStorage.removeItem(AUTH_KEY); setMerchant(null); }
      finally { setAuthChecking(false); }
    })();
  }, [refresh]);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(''), 3600);
    return () => clearTimeout(t);
  }, [toast]);

  const logout = () => {
    localStorage.removeItem(AUTH_KEY);
    setMerchant(null);
    setData({ metrics: {}, events: [], audit: [] });
    setView('overview');
  };

  if (authChecking) return <div className="min-h-screen app-shell grid place-items-center text-slate-300">Loading ReviveAI…</div>;
  if (!merchant) return <Auth onAuth={async m => { setMerchant(m); await refresh(); }} />;

  return <div className="min-h-screen app-shell text-slate-100">
    <div className="min-h-screen app-surface">
      <Shell merchant={merchant} view={view} setView={setView} onLogout={logout}>
        <MainView view={view} merchant={merchant} data={data} refresh={refresh} setToast={setToast} />
      </Shell>
    </div>
    {toast && <div className="fixed bottom-5 right-5 z-[80] max-w-sm rounded-xl border border-cyan/20 bg-slate-950 px-4 py-3 text-sm shadow-2xl">{toast}</div>}
  </div>;
}

function Shell({ merchant, view, setView, onLogout, children }) {
  const nav = [
    ['overview', 'Overview', '▦'],
    ['risk', 'Risk', '△'],
    ['recovery', 'Recovery', '↗'],
    ['sources', 'Sources', '◫'],
    ['settings', 'Settings', '⚙'],
  ];
  return <div className="lg:grid lg:grid-cols-[250px_1fr]">
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[250px] flex-col sidebar-shell px-4 py-5 lg:flex">
      <button className="mb-10 flex items-center gap-3 px-3 text-left" onClick={() => setView('overview')}>
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-electric text-xl font-black">R</div>
        <div><div className="font-black tracking-[.18em]">REVIVE</div><div className="text-xs text-slate-400">Revenue Intelligence</div></div>
      </button>
      <nav className="space-y-2">
        {nav.map(([id, label, icon]) => <button key={id} onClick={() => setView(id)} className={`nav-btn w-full px-4 py-3 text-left transition flex items-center gap-3 ${view === id ? 'nav-btn-active' : 'nav-btn-idle'}`}>
          <span className="w-5 text-center">{icon}</span><span className="text-sm font-semibold">{label}</span>
        </button>)}
      </nav>
      <div className="mt-auto sidebar-status p-4"><div className="text-[10px] uppercase tracking-[.2em] text-cyan">Agent status</div><div className="mt-2 flex items-center gap-2 text-sm"><span className="h-2 w-2 rounded-full bg-good"/>Online</div><div className="mt-1 text-xs text-slate-500">Watching {merchant.payment_gateway?.toUpperCase() || 'PAYU'}</div></div>
    </aside>
    <main className="min-h-screen lg:col-start-2 px-4 pb-10 pt-5 sm:px-6 lg:px-10">
      <header className="mb-6 flex items-center justify-between gap-4 sticky top-0 z-30 py-2">
        <button onClick={() => setView('overview')} className="text-left">
          <div className="text-xs font-bold uppercase tracking-[.22em] text-cyan">Revenue intelligence</div>
          <div className="mt-1 text-sm text-slate-300">Find revenue that's slipping away. <span className="text-slate-500">Detect. Diagnose. Decide. Recover.</span></div>
        </button>
        <AccountMenu merchant={merchant} onLogout={onLogout} onSettings={() => setView('settings')} />
      </header>
      <div className="mb-5 flex gap-2 overflow-x-auto lg:hidden">
        {nav.map(([id, label]) => <button key={id} onClick={() => setView(id)} className={`whitespace-nowrap ${btn} ${view === id ? 'border-electric bg-electric/15 text-white' : ''}`}>{label}</button>)}
      </div>
      {children}
    </main>
  </div>;
}

function AccountMenu({ merchant, onLogout, onSettings }) {
  const [open, setOpen] = useState(false);
  return <div className="relative">
    <button onClick={() => setOpen(v => !v)} className="account-chip flex items-center gap-3 rounded-2xl px-3 py-2" aria-expanded={open}>
      <div className="grid h-9 w-9 place-items-center rounded-xl brand-mark font-black">R</div>
      <div className="hidden text-left sm:block"><div className="text-sm font-semibold">{merchant.business_name}</div><div className="text-xs text-slate-400">{merchant.sender_email || merchant.login_email}</div></div>
      <span className="text-slate-400">⌄</span>
    </button>
    {open && <div className={`${panel} absolute right-0 z-50 mt-2 w-80 rounded-2xl p-4 shadow-2xl`}>
      <div className="text-xs font-bold uppercase tracking-[.18em] text-cyan">Account details</div>
      <div className="mt-4 space-y-2 text-sm"><Row l="Business" v={merchant.business_name}/><Row l="Login" v={merchant.login_email}/><Row l="Recovery sender" v={merchant.sender_email}/><Row l="Gateway" v={String(merchant.payment_gateway || 'payu').toUpperCase()}/><Row l="Mode" v={merchant[`${merchant.payment_gateway || 'payu'}_mode`] || 'test'}/></div>
      <div className="mt-4 flex gap-2"><button className={`flex-1 ${btn}`} onClick={onSettings}>Settings</button><button className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-2.5 text-sm font-semibold text-red-300" onClick={onLogout}>Log out</button></div>
    </div>}
  </div>;
}
const Row = ({ l, v }) => <div className="flex justify-between gap-4"><span className="text-slate-500">{l}</span><span className="max-w-[190px] truncate text-right text-slate-200">{v || '—'}</span></div>;

function Auth({ onAuth }) {
  const [mode, setMode] = useState('login');
  const [f, setF] = useState({ business_name: '', login_email: '', password: '', sender_email: '', use_demo_email: true, smtp_host: '', smtp_port: 587, smtp_username: '', smtp_password: '' });
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false);
  const update = (k, v) => setF(s => ({ ...s, [k]: v }));
  const submit = async e => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const body = mode === 'login' ? { login_email: f.login_email.trim(), password: f.password } : { ...f, business_name: f.business_name.trim(), login_email: f.login_email.trim(), sender_email: f.sender_email.trim(), smtp_port: Number(f.smtp_port) || 587 };
      const out = await api(mode === 'login' ? '/auth/login' : '/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      localStorage.setItem(AUTH_KEY, out.token); await onAuth(out.merchant);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return <div className="fixed inset-0 z-50 grid place-items-center modal-backdrop p-4"><form onSubmit={submit} className={`${panel} w-full max-w-xl rounded-3xl p-7`}>
    <div className="brand-kicker">REVIVEAI / REVENUE OS</div><h1 className="mt-2 text-3xl font-black">{mode === 'login' ? 'Welcome back' : 'Create merchant ID'}</h1><p className="mt-2 text-sm text-slate-400">Revenue recovery for modern merchants.</p>
    <div className="mt-6 grid grid-cols-2 gap-2 rounded-xl bg-white/5 p-1"><button type="button" onClick={() => setMode('login')} className={`rounded-lg py-2 text-sm ${mode === 'login' ? 'bg-electric text-white' : 'text-slate-400'}`}>Log in</button><button type="button" onClick={() => setMode('signup')} className={`rounded-lg py-2 text-sm ${mode === 'signup' ? 'bg-electric text-white' : 'text-slate-400'}`}>Create merchant ID</button></div>
    <div className="mt-5 grid gap-3">{mode === 'signup' && <Field label="Business name" value={f.business_name} set={v => update('business_name', v)} />}<Field label="Login email" type="email" value={f.login_email} set={v => update('login_email', v)} /><Field label="Password" type="password" value={f.password} set={v => update('password', v)} />
      {mode === 'signup' && <><Field label="Recovery sender email" type="email" value={f.sender_email} set={v => update('sender_email', v)} /><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={f.use_demo_email} onChange={e => update('use_demo_email', e.target.checked)} /> Use demo email mode for now</label>{!f.use_demo_email && <div className="grid grid-cols-2 gap-3"><Field label="SMTP host" value={f.smtp_host} set={v => update('smtp_host', v)} /><Field label="SMTP port" value={f.smtp_port} set={v => update('smtp_port', v)} /><Field label="SMTP username" value={f.smtp_username} set={v => update('smtp_username', v)} /><Field label="SMTP password/app password" type="password" value={f.smtp_password} set={v => update('smtp_password', v)} /></div>}</>}
    </div>
    {err && <div className="mt-3 rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-300">{err}</div>}
    <button disabled={busy} className={`mt-5 w-full ${primary}`}>{busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create merchant ID'}</button>
  </form></div>;
}
const Field = ({ label, value, set, type = 'text', placeholder = '' }) => <label className="grid gap-1.5 text-xs text-slate-400">{label}<input className={input} type={type} value={value ?? ''} placeholder={placeholder} onChange={e => set(e.target.value)} /></label>;

function MainView({ view, merchant, data, refresh, setToast }) {
  if (view === 'overview') return <Overview data={data} merchant={merchant} refresh={refresh} setToast={setToast} />;
  if (view === 'risk') return <Risk events={data.events} refresh={refresh} setToast={setToast} />;
  if (view === 'recovery') return <Recovery items={data.events} refresh={refresh} setToast={setToast} />;
  if (view === 'sources') return <Sources merchant={merchant} refresh={refresh} setToast={setToast} />;
  return <Settings merchant={merchant} refresh={refresh} setToast={setToast} />;
}

function Overview({ data, merchant, refresh, setToast }) {
  const m = data.metrics || {}; const events = data.events || []; const active = events.filter(e => !isTerminal(e) && !['EXECUTED', 'recovered'].includes(String(e.action_status || '').toLowerCase()));
  const [metric, setMetric] = useState(null); const [hovered, setHovered] = useState(null); const [sim, setSim] = useState(false); const [detail, setDetail] = useState(null);
  const execute = async id => { try { const out = await api(`/events/${encodeURIComponent(id)}/execute`, { method: 'POST' }); setToast(out.message || 'Recovery action executed.'); setDetail(null); await refresh(); } catch (e) { setToast(e.message); } };
  const cards = [
    ['risk', 'Revenue at risk', money(m.revenue_at_risk), `${active.length} actionable leak${active.length === 1 ? '' : 's'}`, 'Open exposure currently being monitored.'],
    ['expected', 'Expected recovery', money(m.expected_recovery), `${pct(m.revenue_at_risk ? m.expected_recovery / m.revenue_at_risk : 0)} weighted recovery`, 'Probability-weighted opportunity from the model.'],
    ['recovered', 'Recovered', money(m.recovered), `${events.filter(e => e.recovered).length} confirmed outcome${events.filter(e => e.recovered).length === 1 ? '' : 's'}`, 'Revenue confirmed through sync, webhook or demo confirmation.'],
    ['actions', 'Active actions', String(m.active_actions ?? 0), 'Awaiting outcome', 'Actions already executed but not yet reconciled.'],
  ];
  return <div className="space-y-5">
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"><div><div className="brand-kicker">{String(merchant.payment_gateway || 'payu').toUpperCase()} / {merchant[`${merchant.payment_gateway || 'payu'}_mode`] || 'test'} mode</div><h1 className="mt-2 text-3xl font-black">Find revenue that's slipping away.</h1><p className="mt-1 text-sm text-slate-400">Your agent is watching payments, checkouts and invoices.</p></div><div className="flex gap-2"><button className={btn} onClick={refresh}>↻ Refresh</button><button className={primary} onClick={() => setSim(true)}>＋ Simulate leak</button></div></div>
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{cards.map(([id, l, v, n, more]) => <button key={id} onClick={() => setMetric(metric === id ? null : id)} onMouseEnter={() => setHovered(id)} onMouseLeave={() => setHovered(null)} className={`${panel} metric-card p-5 text-left ${hovered === id ? 'metric-card-live' : ''}`}><div className="flex items-center justify-between"><div className="text-xs uppercase tracking-[.14em] text-slate-400">{l}</div><span className="text-slate-600">{metric === id ? '−' : '+'}</span></div><div className={`mt-3 text-3xl font-black ${id === 'recovered' ? 'text-good' : ''}`}>{v}</div><div className="mt-4 metric-bar"><span style={{ width: id === 'risk' ? '72%' : id === 'expected' ? '56%' : id === 'recovered' ? '38%' : '64%' }} /></div><div className="mt-3 text-xs text-slate-500">{metric === id ? more : n}</div></button>)}</section>
    <section className="grid gap-5 xl:grid-cols-[1fr_340px]">
      <div className={`${panel} overflow-hidden`}><div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><div><h2 className="text-xl font-bold">Highest-priority revenue leaks</h2><p className="text-sm text-slate-400">Active opportunities ranked by risk and recovery potential.</p></div><span className="rounded-full border border-cyan/20 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.12em] text-cyan">LIVE</span></div>
        <div className="overflow-auto"><table className="w-full text-left"><thead className="bg-white/5 text-[10px] uppercase tracking-[.14em] text-slate-500"><tr><th className="px-5 py-3">Customer</th><th>Event</th><th>Risk</th><th>Recovery</th><th className="pr-5">Action</th></tr></thead><tbody>{active.slice().sort((a,b)=>(b.risk_score||0)-(a.risk_score||0)).slice(0,8).map(e => <tr key={e.id} className="border-t border-white/5 hover:bg-white/[0.03]"><td className="px-5 py-4"><button onClick={() => setDetail(e)} className="text-left"><div className="font-semibold hover:text-cyan">{e.customer}</div><div className="text-xs text-slate-500">{e.customer_email || 'No email'}</div></button></td><td><div className="text-sm">{pretty(e.event_type)}</div><div className="text-xs text-slate-500">{e.source || 'simulator'}</div></td><td><span className="rounded-full border border-red-400/30 px-2 py-1 text-xs text-red-300">{e.risk_score ?? 0}/100</span></td><td className="font-bold text-good">{pct(e.recovery_probability)}</td><td className="pr-5"><button className={btn} onClick={() => execute(e.id)}>Execute ↗</button></td></tr>)}</tbody></table>{!active.length && <div className="p-12 text-center text-slate-500">No active leaks detected. Simulate one to start the agent.</div>}</div></div>
      <Agent events={events} onExecute={execute} />
    </section>
    <Audit logs={data.audit || []} refresh={refresh} />
    {sim && <Simulate onClose={() => setSim(false)} onDone={async () => { setSim(false); await refresh(); }} setToast={setToast} />}
    {detail && <EventDetail event={detail} onClose={() => setDetail(null)} onExecute={execute} />}
  </div>;
}

function Agent({ events, onExecute }) { const latest = events[0]; return <div className={`${panel} p-5`}><div className="flex items-center justify-between"><div><h2 className="text-xl font-bold">Agent decision</h2><p className="text-sm text-slate-400">Latest recommendation and outcome.</p></div><span className="h-2.5 w-2.5 rounded-full bg-electric"/></div>{latest ? <div className="mt-6"><div className="text-xs font-bold uppercase tracking-[.15em] text-cyan">Action result</div><div className="mt-3 text-2xl font-black">{pretty(latest.recommended_action || 'Analyze')}</div><div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-xl border border-white/10 bg-white/5 p-3"><div className="text-xs text-slate-500">Amount</div><div className="mt-1 font-bold">{money(latest.amount)}</div></div><div className="rounded-xl border border-white/10 bg-white/5 p-3"><div className="text-xs text-slate-500">Status</div><div className="mt-1 font-bold">{latest.recovered ? 'Recovered' : pretty(latest.lifecycle_status || 'Recommended')}</div></div></div><div className="mt-4 rounded-xl border-l-2 border-cyan bg-black/20 p-4 text-sm text-slate-300">{latest.action_reason || latest.risk_reason}</div>{!isTerminal(latest)&&!['EXECUTED','recovered'].includes(String(latest.action_status||'').toLowerCase())&&<button className={`mt-4 w-full ${primary}`} onClick={() => onExecute(latest.id)}>Execute recovery</button>}</div> : <div className="mt-10 text-center text-slate-500">Simulate an event to see agent work and recommendations.</div>}</div> }

function Audit({ logs, refresh }) { return <div className={`${panel} overflow-hidden`}><div className="flex items-center justify-between border-b border-white/10 px-5 py-4"><div><h2 className="text-xl font-bold">Audit logs</h2><p className="text-sm text-slate-400">Recent agent decisions, connector events and recovery outcomes.</p></div><button className={btn} onClick={refresh}>Refresh logs</button></div><div className="max-h-72 overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-950 text-slate-500"><tr><th className="px-5 py-3">Time</th><th>Action</th><th>Status</th><th>Details</th></tr></thead><tbody>{logs.map((l,i)=><tr key={l.id || i} className="border-t border-white/5"><td className="px-5 py-3 whitespace-nowrap">{l.created_at ? new Date(l.created_at).toLocaleString() : '—'}</td><td>{pretty(l.action || '')}</td><td><span className="rounded-full border border-white/10 px-2 py-1">{pretty(l.status || '')}</span></td><td className="max-w-[560px] truncate text-slate-400">{l.detail || l.message || '—'}</td></tr>)}</tbody></table>{!logs.length&&<div className="p-6 text-center text-slate-500">No audit records yet.</div>}</div></div> }

function Simulate({ onClose, onDone, setToast }) { const [f,setF]=useState({customer:'Demo Customer',customer_email:'demo@example.com',amount:18500,event_type:'payment_failed',failure_reason:'temporary_decline',previous_success_rate:0.7,customer_value:50000,prior_contacts:0,days_since_last_success:7,days_overdue:7,consent_to_email:true}); const [busy,setBusy]=useState(false); const set=(k,v)=>setF(s=>({...s,[k]:v})); const submit=async e=>{e.preventDefault();setBusy(true);try{await api('/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...f,amount:Number(f.amount),previous_success_rate:Number(f.previous_success_rate),customer_value:Number(f.customer_value),prior_contacts:Number(f.prior_contacts),days_since_last_success:Number(f.days_since_last_success),days_overdue:Number(f.days_overdue),currency:'INR',source:'simulator'})});setToast('Revenue leak simulated.');await onDone()}catch(e){setToast(e.message)}finally{setBusy(false)}};return <Modal title="Create a revenue leak" onClose={onClose}><form onSubmit={submit} className="grid gap-3"><div className="grid grid-cols-2 gap-3"><Field label="Customer" value={f.customer} set={v=>set('customer',v)}/><Field label="Customer email" type="email" value={f.customer_email} set={v=>set('customer_email',v)}/></div><Field label="Amount (INR)" value={f.amount} set={v=>set('amount',v)}/><label className="grid gap-1.5 text-xs text-slate-400">Event type<select className={input} value={f.event_type} onChange={e=>set('event_type',e.target.value)}><option value="payment_failed">Payment Failed</option><option value="checkout_abandoned">Checkout Abandoned</option><option value="invoice_overdue">Invoice Overdue</option></select></label><div className="grid grid-cols-2 gap-3"><Field label="Previous success rate (0–1)" value={f.previous_success_rate} set={v=>set('previous_success_rate',v)}/><Field label="Customer value (INR)" value={f.customer_value} set={v=>set('customer_value',v)}/></div><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={f.consent_to_email} onChange={e=>set('consent_to_email',e.target.checked)}/> Customer has consented to recovery email</label><div className="flex justify-end gap-2 pt-2"><button type="button" className={btn} onClick={onClose}>Cancel</button><button disabled={busy} className={primary}>{busy?'Analyzing…':'Analyze leak'}</button></div></form></Modal> }

function EventDetail({event,onClose,onExecute}) { return <Modal title={event.customer} onClose={onClose}><div className="grid gap-4"><div className="grid grid-cols-2 gap-3"><Info label="Event" value={pretty(event.event_type)}/><Info label="Amount" value={money(event.amount)}/><Info label="Risk" value={`${event.risk_score ?? 0}/100`}/><Info label="Recovery" value={pct(event.recovery_probability)}/><Info label="Recommendation" value={pretty(event.recommended_action)}/><Info label="Lifecycle" value={pretty(event.lifecycle_status || '')}/></div><div className="rounded-xl border-l-2 border-cyan bg-black/20 p-4 text-sm text-slate-300">{event.action_reason || event.risk_reason}</div>{!isTerminal(event)&&!['EXECUTED','recovered'].includes(String(event.action_status||'').toLowerCase())&&<button className={primary} onClick={()=>onExecute(event.id)}>Execute recommended action</button>}</div></Modal> }
const Info=({label,value})=><div className="rounded-xl border border-white/10 bg-white/[.03] p-3"><div className="text-[10px] uppercase tracking-[.15em] text-slate-500">{label}</div><div className="mt-1 font-semibold">{value}</div></div>;
const Modal=({title,onClose,children})=><div className="fixed inset-0 z-[70] grid place-items-center modal-backdrop p-4"><div className={`${panel} w-full max-w-2xl rounded-3xl p-6 shadow-2xl`}><div className="flex items-center justify-between gap-4"><h2 className="text-2xl font-black">{title}</h2><button className={btn} onClick={onClose}>Close</button></div><div className="mt-5">{children}</div></div></div>;

function Risk({events,refresh,setToast}) { const [selected,setSelected]=useState(null); const execute=async id=>{try{const o=await api(`/events/${encodeURIComponent(id)}/execute`,{method:'POST'});setToast(o.message||'Recovery action executed.');setSelected(null);await refresh()}catch(e){setToast(e.message)}}; return <div><PageHead title="Risk intelligence" subtitle="Inspect the model's assessment of every revenue leak." refresh={refresh}/><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{events.map(e=><button key={e.id} onClick={()=>setSelected(e)} className={`${panel} p-5 text-left`}><div className="flex items-center justify-between"><div className="font-bold">{e.customer}</div><span className="text-xs text-slate-400">{pretty(e.lifecycle_status||'detected')}</span></div><div className="mt-3 text-3xl font-black">{money(e.amount)}</div><div className="mt-2 flex items-center gap-3"><span className="rounded-full border border-red-400/30 px-2 py-1 text-xs text-red-300">Risk {e.risk_score}/100</span><span className="font-bold text-good">{pct(e.recovery_probability)}</span></div><p className="mt-4 line-clamp-3 text-sm text-slate-400">{e.risk_reason}</p></button>)}</div>{selected&&<EventDetail event={selected} onClose={()=>setSelected(null)} onExecute={execute}/>}</div> }

function Recovery({items,refresh,setToast}) { const [emailEvent,setEmailEvent]=useState(null); const exec=async id=>{try{const o=await api(`/events/${encodeURIComponent(id)}/execute`,{method:'POST'});setToast(o.message||'Action executed.');await refresh()}catch(e){setToast(e.message)}}; const sync=async id=>{try{const o=await api(`/events/${encodeURIComponent(id)}/sync-payment-link`,{method:'POST'});setToast(o.message || `Status: ${o.status || 'checked'}`);await refresh()}catch(e){setToast(e.message)}}; return <div><PageHead title="Recovery actions" subtitle="Execute, reconcile and communicate recovery interventions." refresh={refresh}/><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map(e=><div key={e.id} className={`${panel} p-5`}><div className="flex items-center justify-between"><div className="font-bold">{pretty(e.recommended_action)}</div><span className="text-xs text-slate-400">{pretty(e.lifecycle_status||'detected')}</span></div><div className="mt-3 text-3xl font-black">{money(e.amount)}</div><p className="mt-2 text-sm text-slate-300">{e.customer}</p><p className="mt-2 text-sm text-slate-400">{e.action_reason}</p>{e.recovery_link_url&&<div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3"><div className="text-xs text-slate-500">Payment link</div><a className="mt-1 block break-all text-sm text-cyan underline" href={e.recovery_link_url} target="_blank" rel="noreferrer">Open payment link</a><button className={`mt-3 ${btn}`} onClick={()=>sync(e.id)}>↻ Sync status</button></div>}<div className="mt-4 flex flex-wrap gap-2">{!isTerminal(e)&&!['EXECUTED','recovered'].includes(String(e.action_status||'').toLowerCase())&&<button className={primary} onClick={()=>exec(e.id)}>Execute</button>}{e.customer_email&&<button className={btn} onClick={()=>setEmailEvent(e)}>Email preview</button>}{!e.recovered&&<button className={btn} onClick={async()=>{try{await api(`/events/${encodeURIComponent(e.id)}/confirm-recovered`,{method:'POST'});setToast('Marked recovered for demo.');await refresh()}catch(err){setToast(err.message)}}}>Mark recovered</button>}</div></div>)}</div>{emailEvent&&<EmailModal event={emailEvent} onClose={()=>setEmailEvent(null)} setToast={setToast}/>}</div> }

function EmailModal({event,onClose,setToast}) { const [preview,setPreview]=useState(null); const [consent,setConsent]=useState(false); const [busy,setBusy]=useState(false); const [recipient,setRecipient]=useState(event.customer_email||''); useEffect(()=>{api(`/events/${encodeURIComponent(event.id)}/email-preview`).then(setPreview).catch(e=>setToast(e.message))},[event.id,setToast]); const send=async()=>{if(!consent){setToast('Confirm email consent before sending.');return}setBusy(true);try{const o=await api('/recovery/email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:event.id,recipient,consent:true})});setToast(o.message||'Recovery email sent.');onClose()}catch(e){setToast(e.message)}finally{setBusy(false)}}; return <Modal title="Recovery email" onClose={onClose}><div className="grid gap-4">{preview ? <><Info label="From" value={preview.sender}/><Info label="To" value={recipient}/><Info label="Subject" value={preview.subject}/><div className="rounded-xl border border-white/10 bg-[#07112e] p-4 whitespace-pre-wrap text-sm leading-6 text-slate-300">{preview.body}</div></> : <div className="text-slate-400">Loading preview…</div>}<Field label="Recipient" type="email" value={recipient} set={setRecipient}/><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I confirm this recipient has consented to recovery email.</label><button disabled={busy||!preview} className={primary} onClick={send}>{busy?'Sending…':'Send recovery email'}</button></div></Modal> }

function PageHead({title,subtitle,refresh}){return <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-3xl font-black">{title}</h1><p className="mt-1 text-sm text-slate-400">{subtitle}</p></div><button className={btn} onClick={refresh}>↻ Refresh</button></div>}

function Sources({merchant,refresh,setToast}) {
  const [gateway,setGateway]=useState(merchant?.payment_gateway||'payu'); const [payu,setPayu]=useState({merchant_id:'',client_id:'',client_secret:'',key:'',salt:'',mode:'test',configured:false}); const [razor,setRazor]=useState({key_id:'',key_secret:'',webhook_secret:'',mode:'test',configured:false,webhook_configured:false}); const [invoice,setInvoice]=useState(null); const [busy,setBusy]=useState(''); const [checkout,setCheckout]=useState({session_id:'demo-checkout',customer:'Checkout Customer',amount:5000});
  const load=useCallback(async()=>{try{const [p,r,m]=await Promise.all([api('/integrations/payu/settings'),api('/integrations/razorpay/settings'),api('/auth/me')]);setGateway(m.payment_gateway||'payu');setPayu(v=>({...v,...p,client_secret:'',salt:''}));setRazor(v=>({...v,...r,key_secret:'',webhook_secret:''}))}catch(e){setToast(e.message)}},[setToast]); useEffect(()=>{load()},[load]);
  const activate=async g=>{try{setBusy(`activate-${g}`);await api('/integrations/payment-gateway',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({gateway:g})});setGateway(g);setToast(`${g.toUpperCase()} is now the active gateway.`);await refresh()}catch(e){setToast(e.message)}finally{setBusy('')}};
  const savePayU=async()=>{try{setBusy('save-payu');const o=await api('/integrations/payu/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payu,client_secret:payu.client_secret||undefined,key:payu.key||undefined,salt:payu.salt||undefined})});setGateway('payu');setToast(`PayU saved. ${o.webhook_url}`);await refresh();await load()}catch(e){setToast(e.message)}finally{setBusy('')}};
  const testPayU=async()=>{try{setBusy('test-payu');const o=await api('/integrations/payu/test-merchant');setToast(o.ok?`PayU ${String(o.mode||'test').toUpperCase()} connected.`:o.message||'PayU connection failed')}catch(e){setToast(e.message)}finally{setBusy('')}};
  const saveRazor=async()=>{try{setBusy('save-razor');const o=await api('/integrations/razorpay/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...razor,key_secret:razor.key_secret||undefined,webhook_secret:razor.webhook_secret||undefined})});setGateway('razorpay');setToast(`Razorpay saved. ${o.webhook_url}`);await refresh();await load()}catch(e){setToast(e.message)}finally{setBusy('')}};
  const testRazor=async()=>{try{setBusy('test-razor');const o=await api('/integrations/razorpay/test-merchant');setToast(o.ok?`Razorpay ${String(o.mode||'test').toUpperCase()} connected.`:JSON.stringify(o.detail||o.message||'Connection failed'))}catch(e){setToast(e.message)}finally{setBusy('')}};
  const upload=async()=>{if(!invoice){setToast('Choose a CSV file first.');return}try{setBusy('invoice');const form=new FormData();form.append('file',invoice);const o=await api('/invoices/import',{method:'POST',body:form});setToast(`Imported ${o.count} invoice(s).`);setInvoice(null);await refresh()}catch(e){setToast(e.message)}finally{setBusy('')}};
  const checkoutStart=async()=>{try{setBusy('checkout');await api('/checkout/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:checkout.session_id||`demo-${Date.now()}`,customer:checkout.customer,amount:Number(checkout.amount),currency:'INR',stage:'started'})});setToast('Checkout session started.');}catch(e){setToast(e.message)}finally{setBusy('')}};
  const checkoutComplete=async()=>{try{setBusy('checkout');await api('/checkout/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:checkout.session_id,customer:checkout.customer,amount:Number(checkout.amount),currency:'INR',stage:'completed'})});setToast('Checkout completed.');await refresh()}catch(e){setToast(e.message)}finally{setBusy('')}};
  const checkoutScan=async()=>{try{setBusy('scan');const o=await api('/checkouts/scan?older_than_hours=0.01',{method:'POST'});setToast(`Scan created ${o.count} abandoned checkout event(s).`);await refresh()}catch(e){setToast(e.message)}finally{setBusy('')}};
  return <div className="space-y-5">
    <PageHead title="Data sources" subtitle="Connect the payment gateway, checkout stream and invoice feed." refresh={async()=>{await refresh();await load()}} />
    <div className={`${panel} p-5`}><div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"><div><div className="text-xs uppercase tracking-[.18em] text-cyan">Active payment gateway</div><div className="mt-1 text-2xl font-black">{gateway.toUpperCase()}</div><div className="text-sm text-slate-400">New payment-link recoveries use the gateway stored on the event at execution time.</div></div><div className="flex rounded-xl border border-white/10 bg-black/20 p-1"><button disabled={busy!==''||!payu.configured} className={`rounded-lg px-4 py-2 text-sm font-semibold ${gateway==='payu'?'bg-electric text-white shadow-lg':'text-slate-400 hover:text-white'} disabled:cursor-not-allowed disabled:opacity-40`} onClick={()=>activate('payu')}>{busy==='activate-payu'?'Switching…':'PayU'}</button><button disabled={busy!==''||!razor.configured} className={`rounded-lg px-4 py-2 text-sm font-semibold ${gateway==='razorpay'?'bg-electric text-white shadow-lg':'text-slate-400 hover:text-white'} disabled:cursor-not-allowed disabled:opacity-40`} onClick={()=>activate('razorpay')}>{busy==='activate-razorpay'?'Switching…':'Razorpay'}</button></div></div>
      <div className="mt-5 grid gap-5 xl:grid-cols-2"><GatewayCard name="PayU" active={gateway==='payu'} configured={payu.configured} fields={<div className="grid gap-3 md:grid-cols-2"><Field label="Merchant ID" value={payu.merchant_id} set={v=>setPayu({...payu,merchant_id:v})} /><Field label="Client ID" value={payu.client_id} set={v=>setPayu({...payu,client_id:v})} /><Field label="Client secret" type="password" placeholder={payu.configured?'Saved • leave blank to keep':''} value={payu.client_secret} set={v=>setPayu({...payu,client_secret:v})} /><Field label="Key" value={payu.key} set={v=>setPayu({...payu,key:v})}/><Field label="Salt" type="password" placeholder={payu.configured?'Saved • leave blank to keep':''} value={payu.salt} set={v=>setPayu({...payu,salt:v})}/><Select label="Mode" value={payu.mode} set={v=>setPayu({...payu,mode:v})} options={[['test','Test / UAT'],['live','Live']]}/></div>} footer={<><button disabled={busy!==''} className={primary} onClick={savePayU}>{busy==='save-payu'?'Saving…':'Save PayU'}</button><button disabled={busy!==''||!payu.configured} className={btn} onClick={testPayU}>{busy==='test-payu'?'Testing…':'Test connection'}</button></>} /><GatewayCard name="Razorpay" active={gateway==='razorpay'} configured={razor.configured} fields={<div className="grid gap-3 md:grid-cols-2"><Field label="Key ID" value={razor.key_id} set={v=>setRazor({...razor,key_id:v})}/><Field label="Key secret" type="password" placeholder={razor.configured?'Saved • leave blank to keep':''} value={razor.key_secret} set={v=>setRazor({...razor,key_secret:v})}/><Field label="Webhook secret" type="password" placeholder={razor.webhook_configured?'Saved • leave blank to keep':''} value={razor.webhook_secret} set={v=>setRazor({...razor,webhook_secret:v})}/><Select label="Mode" value={razor.mode} set={v=>setRazor({...razor,mode:v})} options={[['test','Test'],['live','Live']]}/></div>} footer={<><button disabled={busy!==''} className={primary} onClick={saveRazor}>{busy==='save-razor'?'Saving…':'Save Razorpay'}</button><button disabled={busy!==''||!razor.configured} className={btn} onClick={testRazor}>{busy==='test-razor'?'Testing…':'Test connection'}</button></>} /></div>
    </div>
    <div className="grid gap-5 xl:grid-cols-2"><div className={`${panel} p-5`}><div className="text-xs uppercase tracking-[.18em] text-cyan">Checkout tracker</div><h2 className="mt-1 text-xl font-bold">Test the abandonment pipeline</h2><p className="mt-2 text-sm text-slate-400">Start a checkout, complete it, or scan unfinished sessions into revenue-risk events.</p><div className="mt-4 grid gap-3 md:grid-cols-3"><Field label="Session ID" value={checkout.session_id} set={v=>setCheckout({...checkout,session_id:v})}/><Field label="Customer" value={checkout.customer} set={v=>setCheckout({...checkout,customer:v})}/><Field label="Amount" value={checkout.amount} set={v=>setCheckout({...checkout,amount:v})}/></div><div className="mt-4 flex flex-wrap gap-2"><button disabled={busy!==''} className={btn} onClick={checkoutStart}>Start checkout</button><button disabled={busy!==''} className={btn} onClick={checkoutComplete}>Complete checkout</button><button disabled={busy!==''} className={primary} onClick={checkoutScan}>{busy==='scan'?'Scanning…':'Scan abandonment'}</button></div></div><div className={`${panel} p-5`}><div className="text-xs uppercase tracking-[.18em] text-cyan">Overdue invoice importer</div><h2 className="mt-1 text-xl font-bold">CSV ingestion</h2><p className="mt-2 text-sm text-slate-400">Required columns: customer, amount, due_date. Optional columns enrich the model.</p><input className="mt-4 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-sm" type="file" accept=".csv" onChange={e=>setInvoice(e.target.files?.[0]||null)}/><div className="mt-3 flex gap-2"><button disabled={busy!==''} className={primary} onClick={upload}>{busy==='invoice'?'Importing…':'Import CSV'}</button>{invoice&&<button className={btn} onClick={()=>setInvoice(null)}>Clear</button>}</div></div></div>
  </div>;
}
const Select=({label,value,set,options})=><label className="grid gap-1.5 text-xs text-slate-400">{label}<select className={input} value={value} onChange={e=>set(e.target.value)}>{options.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>;
function GatewayCard({name,active,configured,fields,footer}){return <div className={`rounded-2xl border p-5 ${active?'border-electric/40 bg-electric/5':'border-white/10 bg-white/[0.03]'}`}><div className="flex items-center justify-between"><div><div className="text-xs uppercase tracking-[.18em] text-cyan">Payment gateway</div><h2 className="mt-1 text-xl font-bold">{name}</h2></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${active?'bg-good/15 text-good':'bg-white/5 text-slate-500'}`}>{active?'Active':configured?'Configured':'Not configured'}</span></div><div className="mt-4">{fields}</div><div className="mt-4 flex flex-wrap gap-2">{footer}</div></div>}

function Settings({merchant,refresh,setToast}) { const [email,setEmail]=useState({sender_email:merchant?.sender_email||'',use_demo_email:Boolean(merchant?.use_demo_email),smtp_host:merchant?.smtp_host||'',smtp_port:merchant?.smtp_port||587,smtp_username:merchant?.smtp_username||'',smtp_password:''}); const [busy,setBusy]=useState(''); useEffect(()=>setEmail({sender_email:merchant?.sender_email||'',use_demo_email:Boolean(merchant?.use_demo_email),smtp_host:merchant?.smtp_host||'',smtp_port:merchant?.smtp_port||587,smtp_username:merchant?.smtp_username||'',smtp_password:''}),[merchant]); const save=async()=>{try{setBusy('save');await api('/auth/email-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...email,smtp_port:Number(email.smtp_port)||587,smtp_password:email.smtp_password||undefined})});setToast('Email settings saved.');await refresh();setEmail(v=>({...v,smtp_password:''}))}catch(e){setToast(e.message)}finally{setBusy('')}}; const test=async()=>{const recipient=window.prompt('Recipient email for test');if(!recipient)return;try{setBusy('test');const o=await api('/auth/email-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient})});setToast(o.message||'Test email sent.')}catch(e){setToast(e.message)}finally{setBusy('')}}; return <div className="space-y-5"><PageHead title="Merchant settings" subtitle="Configure the mailbox Revive uses for recovery emails." refresh={refresh}/><div className={`${panel} max-w-4xl p-5`}><div className="text-xs uppercase tracking-[.18em] text-cyan">Recovery email sender</div><div className="mt-5 grid gap-3 md:grid-cols-2"><Field label="Sender email" type="email" value={email.sender_email} set={v=>setEmail({...email,sender_email:v})}/><Select label="Delivery mode" value={email.use_demo_email?'demo':'smtp'} set={v=>setEmail({...email,use_demo_email:v==='demo'})} options={[['demo','Demo — no real email'],['smtp','Real SMTP delivery']]}/>{!email.use_demo_email&&<><Field label="SMTP host" value={email.smtp_host} set={v=>setEmail({...email,smtp_host:v})}/><Field label="SMTP port" value={email.smtp_port} set={v=>setEmail({...email,smtp_port:v})}/><Field label="SMTP username" value={email.smtp_username} set={v=>setEmail({...email,smtp_username:v})}/><Field label="SMTP password / app password" type="password" placeholder="Leave blank to keep saved credential" value={email.smtp_password} set={v=>setEmail({...email,smtp_password:v})}/></>}</div><div className="mt-5 flex flex-wrap gap-2"><button disabled={busy!==''} className={primary} onClick={save}>{busy==='save'?'Saving…':'Save settings'}</button><button disabled={busy!==''} className={btn} onClick={test}>{busy==='test'?'Sending…':'Send test email'}</button></div></div></div>}

createRoot(document.getElementById('root')).render(<App/>);
