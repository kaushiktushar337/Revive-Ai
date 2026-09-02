const API = "http://localhost:8000/api";
let latestEvents = [];

const currency = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);
const prettyAction = (s) => (s || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const pct = (n) => `${Math.round((n || 0) * 100)}%`;

async function getDashboard() {
  const r = await fetch(`${API}/dashboard`);
  if (!r.ok) throw new Error("Backend unavailable");
  return r.json();
}

function renderDashboard(data) {
  latestEvents = data.events || [];
  const m = data.metrics;
  document.querySelector('#riskMetric').textContent = currency(m.revenue_at_risk);
  document.querySelector('#expectedMetric').textContent = currency(m.expected_recovery);
  document.querySelector('#recoveredMetric').textContent = currency(m.recovered);
  document.querySelector('#eventsMetric').textContent = m.events;

  const sorted = [...latestEvents].sort((a,b) => b.risk_score - a.risk_score);
  const table = document.querySelector('#eventTable');
  table.innerHTML = sorted.length ? sorted.map(e => `
    <div class="event-row">
      <div class="event-main"><strong>${e.customer}</strong><span>${prettyAction(e.event_type)}</span></div>
      <div><div class="amount">${currency(e.amount)}</div><div class="cell-sub">at risk</div></div>
      <div><div class="prob">${pct(e.recovery_probability)}</div><div class="cell-sub">recovery</div></div>
      <div><div class="risk-badge">Risk ${e.risk_score}/100</div><div class="cell-sub" style="margin-top:6px">${prettyAction(e.recommended_action)}</div></div>
      <div><button class="action-btn" onclick="executeEvent('${e.id}')">Execute</button></div>
    </div>`).join('') : '<div class="empty-state">No events yet.</div>';

  renderRisk(sorted);
  renderRecovery(sorted);
  renderAudit(sorted);
}

function renderRisk(events) {
  document.querySelector('#riskGrid').innerHTML = events.map(e => `
    <div class="small-card">
      <div class="card-top"><h3>${e.customer}</h3><span class="risk-badge">${e.risk_score}/100</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <div class="action-pill">${pct(e.recovery_probability)} recovery</div>
      <p>${e.risk_reason}</p>
      <p>${e.action_reason}</p>
    </div>`).join('') || '<div class="empty-state">No revenue-risk events.</div>';
}

function renderRecovery(events) {
  document.querySelector('#recoveryGrid').innerHTML = events.map(e => `
    <div class="small-card">
      <div class="card-top"><h3>${prettyAction(e.recommended_action)}</h3><span class="action-pill">${e.action_status}</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <p><strong>${e.customer}</strong></p>
      <p>${e.action_reason}</p>
      <button class="action-btn" onclick="executeEvent('${e.id}')">Execute in demo</button>
    </div>`).join('') || '<div class="empty-state">No recovery actions yet.</div>';
}

function renderAudit(events) {
  const rows = events.map(e => `<tr>
    <td>${new Date(e.created_at).toLocaleString()}</td>
    <td>${e.customer}</td>
    <td>${prettyAction(e.event_type)}</td>
    <td>${prettyAction(e.recommended_action)}</td>
    <td>${e.action_status}</td>
    <td>${e.recovered ? 'Recovered' : 'Open'}</td>
  </tr>`).join('');
  document.querySelector('#auditTable').innerHTML = `<table class="audit-table"><thead><tr><th>Time</th><th>Customer</th><th>Event</th><th>Decision</th><th>Status</th><th>Outcome</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function executeEvent(id) {
  const r = await fetch(`${API}/events/${id}/execute`, { method: 'POST' });
  const out = await r.json();
  showDecision(out);
  await refresh();
}
window.executeEvent = executeEvent;

function showDecision(out) {
  document.querySelector('#agentEmpty').classList.add('hidden');
  const box = document.querySelector('#agentDecision');
  box.classList.remove('hidden');
  box.innerHTML = `
    <div class="decision-kicker">ACTION EXECUTED</div>
    <div class="decision-action">${prettyAction(out.action)}</div>
    <div class="decision-meta">
      <div class="mini-stat"><span>Amount</span><strong>${currency(out.amount)}</strong></div>
      <div class="mini-stat"><span>Outcome</span><strong>${out.recovered ? 'Recovered' : out.status}</strong></div>
    </div>
    <div class="reason-box">${out.message}</div>`;
}

async function refresh() {
  try {
    const data = await getDashboard();
    renderDashboard(data);
  } catch (err) {
    document.querySelector('#eventTable').innerHTML = '<div class="empty-state">Backend not running. Start FastAPI on port 8000.</div>';
  }
}

function openModal() { document.querySelector('#modal').classList.remove('hidden'); }
function closeModal() { document.querySelector('#modal').classList.add('hidden'); }

document.querySelector('#simulateBtn').addEventListener('click', openModal);
document.querySelector('#closeModal').addEventListener('click', closeModal);
document.querySelector('#resetBtn').addEventListener('click', async () => {
  await fetch(`${API}/reset`, { method: 'POST' });
  await refresh();
});
document.querySelector('#createEventBtn').addEventListener('click', async () => {
  const type = document.querySelector('#eventType').value;
  const payload = {
    event_type: type,
    customer: document.querySelector('#customer').value,
    amount: Number(document.querySelector('#amount').value),
    failure_reason: type === 'payment_failed' ? document.querySelector('#failureReason').value : null,
    previous_success_rate: Number(document.querySelector('#successRate').value),
    prior_contacts: Number(document.querySelector('#priorContacts').value),
    customer_value: Number(document.querySelector('#amount').value) * 4,
    days_since_last_success: 20,
    event_age_hours: 2,
    is_subscription: type === 'payment_failed',
  };
  const r = await fetch(`${API}/events`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  const out = await r.json();
  showDecision({ ...out, action: out.recommended_action, amount: out.amount, status: 'recommended', recovered: false, message: out.action_reason });
  closeModal();
  await refresh();
});

document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
  btn.classList.add('active');
  document.querySelector(`#${btn.dataset.view}`).classList.add('active-view');
}));

refresh();
