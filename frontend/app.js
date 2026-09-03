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
      <div><div class="amount">${currency(e.amount)}</div><div class="cell-sub">${esc(e.lifecycle_status || e.action_status || 'DETECTED')}</div></div>
      <div><div class="prob">${pct(e.recovery_probability)}</div><div class="cell-sub">recovery</div></div>
      <div><div class="risk-badge">Risk ${e.risk_score}/100</div><div class="cell-sub" style="margin-top:6px">${prettyAction(e.recommended_action)}</div><div class="cell-sub" style="margin-top:4px">${esc(e.lifecycle_status || 'DETECTED')}</div></div>
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
      ${e.recovery_link_url ? `<div class="reason-box"><strong>Recovery link</strong><br><a href="${esc(e.recovery_link_url)}" target="_blank" rel="noopener">Open payment link</a>${e.recovered ? '' : `<br><button class="action-btn" style="margin-top:8px" onclick="syncPaymentLink('${esc(e.id)}')">Sync payment status</button>`}</div>` : ''}
      ${e.recovered_amount ? `<div class="reason-box"><strong>Recovered</strong><br>${currency(e.recovered_amount)} · ${esc(e.outcome_source || 'confirmed')}</div>` : ''}
      <div class="button-row">
        <button class="action-btn" onclick="executeEvent('${esc(e.id)}')">Execute</button>
        ${e.customer_email ? `<button class="action-btn" onclick="sendRecoveryEmail('${esc(e.id)}','${esc(e.customer_email)}')">Send email</button>` : ''}
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
    <td>${esc(e.lifecycle_status || e.action_status)}</td>
    <td>${e.recovered ? `Recovered · ${currency(e.recovered_amount || e.amount)}` : 'Open'}</td>
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

async function sendRecoveryEmail(id, recipient) {
  try {
    const preview = await request(`/events/${encodeURIComponent(id)}/email-preview`);
    const consent = window.confirm(`Send this recovery email to ${recipient}?\n\nSubject: ${preview.subject}`);
    if (!consent) return;
    const out = await request('/recovery/email', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ event_id:id, recipient, consent:true }) });
    showDecision({ action:'send_recovery_email', status:'sent', recovered:false, amount:0, message:`Recovery email sent to ${out.recipient}${out.mocked ? ' (demo mode)' : ''}.` });
    await refresh();
  } catch (err) { showError(err.message); }
}
window.sendRecoveryEmail = sendRecoveryEmail;

async function syncPaymentLink(id) {
  try {
    const out = await request(`/events/${encodeURIComponent(id)}/sync-payment-link`, { method:'POST' });
    showDecision({ action:'payment_link_sync', status:out.status, lifecycle_status:out.recovered ? 'RECOVERED' : 'AWAITING_OUTCOME', recovered:out.recovered, amount:out.recovered_amount || 0, message: out.recovered ? 'Razorpay confirms the payment link was paid.' : `Razorpay payment link status: ${out.status}` });
    await refresh();
  } catch (err) { showError(err.message); }
}
window.syncPaymentLink = syncPaymentLink;

function showDecision(out) {
  document.querySelector('#agentEmpty').classList.add('hidden');
  const box = document.querySelector('#agentDecision');
  box.classList.remove('hidden');
  box.innerHTML = `
    <div class="decision-kicker">${out.recovered ? 'RECOVERY CONFIRMED' : 'ACTION RESULT'}</div>
    <div class="decision-action">${prettyAction(out.action)}</div>
    ${out.lifecycle_status ? `<div class="reason-box"><strong>Lifecycle</strong><br>${esc(out.lifecycle_status)}</div>` : ''}
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
    customer_email: document.querySelector('#customerEmail').value.trim(),
    consent_to_email: true,
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
    const out = await request('/integrations/razorpay/test-merchant');
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


// --- Phase 5 merchant authentication + sender mailbox ---
const AUTH_KEY = 'revive_auth_token';
const getToken = () => localStorage.getItem(AUTH_KEY) || '';
const setToken = t => t ? localStorage.setItem(AUTH_KEY, t) : localStorage.removeItem(AUTH_KEY);
const originalRequest = request;
request = async function(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return originalRequest(path, { ...options, headers });
};

function setAuthError(msg) { document.querySelector('#authError').textContent = msg || ''; }
function setTab(signup) {
  document.querySelector('#loginTab').classList.toggle('active', !signup);
  document.querySelector('#signupTab').classList.toggle('active', signup);
  document.querySelector('#loginForm').classList.toggle('hidden', signup);
  document.querySelector('#signupForm').classList.toggle('hidden', !signup);
  setAuthError('');
}
function showAuth(show=true) { document.querySelector('#authOverlay').classList.toggle('hidden', !show); }
function applyMerchant(m) {
  if (!m) return;
  document.querySelector('#merchantBusiness').textContent = m.business_name || 'Merchant';
  document.querySelector('#merchantSender').textContent = `Recovery email: ${m.sender_email || 'not set'}`;
  document.querySelector('#merchantAvatar').textContent = (m.business_name || 'M')[0].toUpperCase();
  document.querySelector('#settingsBusiness').value = m.business_name || '';
  document.querySelector('#settingsLoginEmail').value = m.login_email || '';
  document.querySelector('#settingsSenderEmail').value = m.sender_email || '';
  document.querySelector('#settingsEmailMode').value = m.use_demo_email ? 'demo' : 'smtp';
  document.querySelector('#settingsSmtpFields').classList.toggle('hidden', m.use_demo_email);
  if (m.smtp_host) document.querySelector('#settingsSmtpHost').value = m.smtp_host;
  if (m.smtp_port) document.querySelector('#settingsSmtpPort').value = m.smtp_port;
  if (m.smtp_username) document.querySelector('#settingsSmtpUser').value = m.smtp_username;
  if (document.querySelector('#rzpMode')) {
    document.querySelector('#rzpMode').value = m.razorpay_mode || 'test';
    document.querySelector('#rzpKeyId').value = m.razorpay_key_id || '';
    document.querySelector('#rzpWebhookUrl').textContent = m.razorpay_webhook_url || 'Not configured';
    document.querySelector('#merchantRazorpayStatus').textContent = m.razorpay_configured ? `${(m.razorpay_mode || 'test').toUpperCase()} connected` : 'Not connected';
    document.querySelector('#merchantRazorpayStatus').className = `status-pill ${m.razorpay_configured ? 'good-status' : ''}`;
  }
}

async function authenticateExisting() {
  if (!getToken()) { showAuth(true); return false; }
  try { const me = await request('/auth/me'); applyMerchant(me); showAuth(false); return true; }
  catch { setToken(''); showAuth(true); return false; }
}

document.querySelector('#loginTab').addEventListener('click', () => setTab(false));
document.querySelector('#signupTab').addEventListener('click', () => setTab(true));
document.querySelector('#signupDemoMode').addEventListener('change', e => document.querySelector('#signupSmtp').classList.toggle('hidden', e.target.checked));
document.querySelector('#settingsEmailMode').addEventListener('change', e => document.querySelector('#settingsSmtpFields').classList.toggle('hidden', e.target.value === 'demo'));

document.querySelector('#loginForm').addEventListener('submit', async e => {
  e.preventDefault(); setAuthError('');
  try {
    const out = await originalRequest('/auth/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({login_email:document.querySelector('#loginEmail').value.trim(), password:document.querySelector('#loginPassword').value}) });
    setToken(out.token); applyMerchant(out.merchant); showAuth(false); await refresh();
  } catch (err) { setAuthError(err.message); }
});

document.querySelector('#signupForm').addEventListener('submit', async e => {
  e.preventDefault(); setAuthError('');
  const demo = document.querySelector('#signupDemoMode').checked;
  try {
    const out = await originalRequest('/auth/register', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      business_name:document.querySelector('#signupBusiness').value.trim(), login_email:document.querySelector('#signupEmail').value.trim(), password:document.querySelector('#signupPassword').value,
      sender_email:document.querySelector('#signupSender').value.trim(), use_demo_email:demo,
      smtp_host:demo?null:document.querySelector('#signupSmtpHost').value.trim()||null, smtp_port:Number(document.querySelector('#signupSmtpPort').value)||587,
      smtp_username:demo?null:document.querySelector('#signupSmtpUser').value.trim()||null, smtp_password:demo?null:document.querySelector('#signupSmtpPassword').value||null
    }) });
    setToken(out.token); applyMerchant(out.merchant); showAuth(false); await refresh();
  } catch (err) { setAuthError(err.message); }
});

document.querySelector('#testEmailBtn').addEventListener('click', async () => {
  const result = document.querySelector('#settingsResult');
  const recipient = document.querySelector('#testEmailRecipient').value.trim();
  if (!recipient) { result.textContent = 'Enter the email address that should receive the test.'; return; }
  result.textContent = 'Sending test email…';
  try {
    const out = await request('/auth/email-test', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({recipient}) });
    result.textContent = `${out.message} Sender: ${out.sender}`;
  } catch (err) { result.textContent = err.message; }
});

document.querySelector('#saveEmailSettingsBtn').addEventListener('click', async () => {
  const demo = document.querySelector('#settingsEmailMode').value === 'demo';
  try {
    const out = await request('/auth/email-settings', { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      sender_email:document.querySelector('#settingsSenderEmail').value.trim(), use_demo_email:demo,
      smtp_host:demo?null:document.querySelector('#settingsSmtpHost').value.trim()||null, smtp_port:Number(document.querySelector('#settingsSmtpPort').value)||587,
      smtp_username:demo?null:document.querySelector('#settingsSmtpUser').value.trim()||null, smtp_password:demo?null:document.querySelector('#settingsSmtpPassword').value||null
    }) });
    const me = await request('/auth/me'); applyMerchant(me);
    document.querySelector('#settingsResult').textContent = 'Email settings saved.';
  } catch(err) { document.querySelector('#settingsResult').textContent = err.message; }
});

document.querySelector('#rzpMode')?.addEventListener('change', e => {
  const key = document.querySelector('#rzpKeyId');
  key.placeholder = e.target.value === 'live' ? 'rzp_live_...' : 'rzp_test_...';
});

document.querySelector('#saveRazorpayBtn')?.addEventListener('click', async () => {
  const result = document.querySelector('#razorpayMerchantResult');
  const mode = document.querySelector('#rzpMode').value;
  const keyId = document.querySelector('#rzpKeyId').value.trim();
  const secret = document.querySelector('#rzpKeySecret').value;
  const webhook = document.querySelector('#rzpWebhookSecret').value;
  if (!keyId || !secret || !webhook) { result.textContent = 'Enter Key ID, Key Secret and Webhook Secret.'; return; }
  result.textContent = 'Saving Razorpay connection…';
  try {
    const out = await request('/integrations/razorpay/settings', { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key_id:keyId,key_secret:secret,webhook_secret:webhook,mode}) });
    result.textContent = `Saved ${mode.toUpperCase()} connection. Webhook URL: ${out.webhook_url}`;
    const me = await request('/auth/me'); applyMerchant(me);
  } catch (err) { result.textContent = err.message; }
});

document.querySelector('#testRazorpayMerchantBtn')?.addEventListener('click', async () => {
  const result = document.querySelector('#razorpayMerchantResult');
  result.textContent = 'Testing Razorpay API…';
  try {
    const out = await request('/integrations/razorpay/test-merchant');
    result.textContent = out.ok ? `Razorpay ${String(out.mode || 'test').toUpperCase()} API connection verified.` : (out.message || `Connection failed (${out.status_code || 'unknown'})`);
  } catch (err) { result.textContent = err.message; }
});

document.querySelector('#logoutBtn').addEventListener('click', () => { setToken(''); showAuth(true); });

// Delay the first application refresh until auth is established.
(async () => { if (await authenticateExisting()) await refresh(); })();
