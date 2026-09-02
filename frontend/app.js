const API = "http://localhost:8000/api";
let latestEvents = [];

const currency = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);
const prettyAction = (s) => (s || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));

async function request(path, options = {}) {
  const r = await fetch(`${API}${path}`, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

async function getDashboard() { return request("/dashboard"); }

function renderDashboard(data) {
  latestEvents = data.events || [];
  const m = data.metrics;
  document.querySelector('#riskMetric').textContent = currency(m.revenue_at_risk);
  document.querySelector('#expectedMetric').textContent = currency(m.expected_recovery);
  document.querySelector('#recoveredMetric').textContent = currency(m.recovered);
  document.querySelector('#activeMetric').textContent = m.active_actions;

  const sorted = [...latestEvents].sort((a,b) => b.risk_score - a.risk_score);
  document.querySelector('#eventTable').innerHTML = sorted.length ? sorted.map(e => `
    <div class="event-row">
      <div class="event-main"><strong>${esc(e.customer)}</strong><span>${prettyAction(e.event_type)} · ${esc(e.source || 'simulator')}</span></div>
      <div><div class="amount">${currency(e.amount)}</div><div class="cell-sub">at risk</div></div>
      <div><div class="prob">${pct(e.recovery_probability)}</div><div class="cell-sub">recovery</div></div>
      <div><div class="risk-badge">Risk ${e.risk_score}/100</div><div class="cell-sub" style="margin-top:6px">${prettyAction(e.recommended_action)}</div></div>
      <div><button class="action-btn" onclick="executeEvent('${esc(e.id)}')">${e.action_status === 'recovered' ? 'Recovered' : 'Execute'}</button></div>
    </div>`).join('') : '<div class="empty-state">No events yet.</div>';

  renderRisk(sorted);
  renderRecovery(sorted);
  renderAudit(sorted);
}

function renderRisk(events) {
  document.querySelector('#riskGrid').innerHTML = events.map(e => `
    <div class="small-card">
      <div class="card-top"><h3>${esc(e.customer)}</h3><span class="risk-badge">${e.risk_score}/100</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <div class="action-pill">${pct(e.recovery_probability)} recovery</div>
      <p>${esc(e.risk_reason)}</p>
      <p><strong>Decision:</strong> ${esc(e.action_reason)}</p>
    </div>`).join('') || '<div class="empty-state">No revenue-risk events.</div>';
}

function renderRecovery(events) {
  document.querySelector('#recoveryGrid').innerHTML = events.map(e => `
    <div class="small-card">
      <div class="card-top"><h3>${prettyAction(e.recommended_action)}</h3><span class="action-pill">${esc(e.action_status)}</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <p><strong>${esc(e.customer)}</strong></p>
      <p>${esc(e.action_reason)}</p>
      <div class="button-row">
        <button class="action-btn" onclick="executeEvent('${esc(e.id)}')">Execute</button>
        ${e.action_status !== 'recovered' && e.recommended_action !== 'do_nothing' && e.recommended_action !== 'escalate' ? `<button class="action-btn success-btn" onclick="confirmRecovered('${esc(e.id)}')">Mark recovered</button>` : ''}
      </div>
    </div>`).join('') || '<div class="empty-state">No recovery actions yet.</div>';
}

function renderAudit(events) {
  const rows = events.map(e => `<tr>
    <td>${new Date(e.created_at).toLocaleString()}</td>
    <td>${esc(e.customer)}</td>
    <td>${prettyAction(e.event_type)}</td>
    <td>${prettyAction(e.recommended_action)}</td>
    <td>${esc(e.action_status)}</td>
    <td>${e.recovered ? 'Recovered' : 'Open'}</td>
  </tr>`).join('');
  document.querySelector('#auditTable').innerHTML = rows ? `<table class="audit-table"><thead><tr><th>Time</th><th>Customer</th><th>Event</th><th>Decision</th><th>Status</th><th>Outcome</th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty-state">No audit events.</div>';
}

async function executeEvent(id) {
  try {
    const out = await request(`/events/${encodeURIComponent(id)}/execute`, { method: 'POST' });
    showDecision(out);
    await refresh();
  } catch (err) { showError(err.message); }
}
window.executeEvent = executeEvent;

async function confirmRecovered(id) {
  try {
    const out = await request(`/events/${encodeURIComponent(id)}/confirm-recovered`, { method: 'POST' });
    showDecision({ action: 'recovery_confirmed', status: out.status, recovered: true, amount: out.amount, message: 'Demo outcome recorded as recovered.' });
    await refresh();
  } catch (err) { showError(err.message); }
}
window.confirmRecovered = confirmRecovered;

function showDecision(out) {
  document.querySelector('#agentEmpty').classList.add('hidden');
  const box = document.querySelector('#agentDecision');
  box.classList.remove('hidden');
  box.innerHTML = `
    <div class="decision-kicker">${out.recovered ? 'RECOVERY CONFIRMED' : 'ACTION RESULT'}</div>
    <div class="decision-action">${prettyAction(out.action)}</div>
    <div class="decision-meta">
      <div class="mini-stat"><span>Amount</span><strong>${currency(out.amount)}</strong></div>
      <div class="mini-stat"><span>Outcome</span><strong>${out.recovered ? 'Recovered' : esc(out.status)}</strong></div>
    </div>
    ${out.reference ? `<div class="reason-box"><strong>Payment reference</strong><br>${esc(out.reference)}</div>` : ''}
    <div class="reason-box">${esc(out.message)}</div>`;
}

function showError(message) {
  document.querySelector('#agentEmpty').textContent = message;
  document.querySelector('#agentEmpty').classList.remove('hidden');
  document.querySelector('#agentDecision').classList.add('hidden');
}

async function refreshHealth() {
  const dot = document.querySelector('#healthDot');
  const text = document.querySelector('#healthText');
  const rz = document.querySelector('#razorpayStatus');
  try {
    const h = await request('/health');
    dot.style.background = 'var(--good)';
    text.textContent = `${h.environment} API online`;
    rz.textContent = h.razorpay.configured ? (h.razorpay.webhook_verification ? 'Configured + signed webhooks' : 'Key configured · webhook secret missing') : 'Demo mode · credentials not set';
    rz.className = `status-pill ${h.razorpay.configured ? 'good-status' : ''}`;
  } catch {
    dot.style.background = 'var(--danger)';
    text.textContent = 'API offline';
    rz.textContent = 'Backend offline';
  }
}

async function refresh() {
  try {
    const data = await getDashboard();
    renderDashboard(data);
    await refreshHealth();
  } catch (err) {
    document.querySelector('#eventTable').innerHTML = '<div class="empty-state">Backend not running. Start FastAPI on port 8000.</div>';
    await refreshHealth();
  }
}

function openModal() { document.querySelector('#modal').classList.remove('hidden'); }
function closeModal() { document.querySelector('#modal').classList.add('hidden'); }

async function createSimulatedEvent() {
  const type = document.querySelector('#eventType').value;
  const payload = {
    event_type: type,
    customer: document.querySelector('#customer').value.trim() || 'Demo Customer',
    amount: Number(document.querySelector('#amount').value),
    failure_reason: type === 'payment_failed' ? document.querySelector('#failureReason').value : null,
    previous_success_rate: Number(document.querySelector('#successRate').value),
    prior_contacts: Number(document.querySelector('#priorContacts').value),
    days_overdue: type === 'invoice_overdue' ? Number(document.querySelector('#daysOverdue').value) : 0,
    customer_value: Number(document.querySelector('#amount').value) * 4,
    days_since_last_success: 20,
    event_age_hours: type === 'checkout_abandoned' ? 3 : 2,
    is_subscription: type === 'payment_failed',
  };
  try {
    const out = await request('/events', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    showDecision({ ...out, action: out.recommended_action, amount: out.amount, status: 'recommended', recovered: false, message: out.action_reason });
    closeModal();
    await refresh();
  } catch (err) { showError(err.message); }
}

document.querySelector('#simulateBtn').addEventListener('click', openModal);
document.querySelector('#closeModal').addEventListener('click', closeModal);
document.querySelector('#resetBtn').addEventListener('click', async () => {
  try { await request('/reset', { method: 'POST' }); await refresh(); showDecision({ action: 'reset_demo', status: 'ready', recovered: false, amount: 0, message: 'Demo data restored.' }); }
  catch (err) { showError(err.message); }
});
document.querySelector('#createEventBtn').addEventListener('click', createSimulatedEvent);

document.querySelector('#simulateCheckoutBtn').addEventListener('click', async () => {
  const session = `demo_${Date.now()}`;
  try {
    await request('/checkout/events', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ session_id:session, customer:'Checkout Demo', amount:24999, stage:'started' }) });
    await request('/checkout/events', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ session_id:session, customer:'Checkout Demo', amount:24999, stage:'started' }) });
    const out = await request('/checkouts/scan?older_than_hours=0', { method:'POST' });
    showDecision({ action:'checkout_abandonment_scan', status:'detected', recovered:false, amount:24999, message:`Scan created ${out.count} abandoned-checkout event(s).` });
    await refresh();
  } catch (err) { showError(err.message); }
});

document.querySelector('#testRazorpayBtn').addEventListener('click', async () => {
  const result = document.querySelector('#razorpayTestResult');
  result.textContent = 'Testing read-only Razorpay API connection…';
  try {
    const out = await request('/integrations/razorpay/test');
    result.textContent = out.ok ? 'Razorpay connection verified.' : (out.message || `Connection failed (${out.status_code || 'unknown'})`);
  } catch (err) {
    result.textContent = err.message;
  }
});

document.querySelector('#uploadInvoiceBtn').addEventListener('click', async () => {
  const file = document.querySelector('#invoiceFile').files[0];
  if (!file) { document.querySelector('#uploadResult').textContent = 'Choose a CSV file first.'; return; }
  const form = new FormData();
  form.append('file', file);
  try {
    const out = await request('/invoices/import', { method:'POST', body: form });
    document.querySelector('#uploadResult').textContent = `Imported ${out.count} overdue invoice(s).`;
    await refresh();
  } catch (err) { document.querySelector('#uploadResult').textContent = err.message; }
});

document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
  btn.classList.add('active');
  document.querySelector(`#${btn.dataset.view}`).classList.add('active-view');
}));

refresh();
