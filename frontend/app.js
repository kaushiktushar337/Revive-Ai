const API = window.REVIVE_API || 'http://127.0.0.1:8000/api';
const AUTH_KEY = 'revive_auth_token';
let latestEvents = [];
let latestAudit = [];

const $ = (s) => document.querySelector(s);
const esc = (value) => { const map = {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}; return String(value ?? "").replace(/[&<>"']/g, c => map[c] || c); };
const currency = (n) => new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:0}).format(n || 0);
const pct = (n) => `${Math.round((n || 0) * 100)}%`;
const pretty = (s) => (s || '').replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
const getToken = () => localStorage.getItem(AUTH_KEY) || '';
const setToken = (t) => t ? localStorage.setItem(AUTH_KEY,t) : localStorage.removeItem(AUTH_KEY);

async function request(path, options={}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

function showView(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const target = document.getElementById(view);
  if (target) target.classList.add('active-view');
  $('#mobileNav')?.classList.add('hidden');
}

document.querySelectorAll('.nav-item').forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.view)));
$('#mobileMenuBtn')?.addEventListener('click', () => $('#mobileNav')?.classList.toggle('hidden'));

function renderEventRows(events) {
  const body = $('#eventTableBody');
  const empty = $('#eventEmpty');
  const active = [...events].filter(e => !e.recovered && !['RECOVERED','CANCELLED','EXPIRED'].includes(String(e.lifecycle_status || '').toUpperCase()));
  if (!active.length) {
    body.innerHTML='';
    empty.textContent='No active leaks detected. Simulate one to start the agent.';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  body.innerHTML = active.sort((a,b)=>(b.risk_score||0)-(a.risk_score||0)).slice(0,8).map(e => `
    <tr class="event-table-row">
      <td><strong class="text-white">${esc(e.customer)}</strong><div class="cell-sub">${esc(e.customer_email || 'No email')}</div></td>
      <td><span class="text-on-surface">${pretty(e.event_type)}</span><div class="cell-sub">${esc(e.source || 'simulator')}</div></td>
      <td><span class="risk-badge">${e.risk_score ?? 0}/100</span></td>
      <td><span class="prob">${pct(e.recovery_probability)}</span></td>
      <td><button class="action-btn action-btn-primary" onclick="executeEvent('${esc(e.id)}')"><span class="material-symbols-outlined">bolt</span> Execute</button></td>
    </tr>`).join('');
}
function renderRisk(events) {
  $('#riskGrid').innerHTML = events.map(e => `
    <article class="small-card">
      <div class="card-top"><h3>${esc(e.customer)}</h3><span class="risk-badge">${e.risk_score ?? 0}/100</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <div class="action-pill">${pct(e.recovery_probability)} recovery</div>
      <p>${esc(e.risk_reason)}</p>
      <div class="reason-box"><strong>Decision</strong><br>${esc(e.action_reason)}</div>
    </article>`).join('') || '<div class="empty-state">No revenue-risk events.</div>';
}

function renderRecovery(events) {
  $('#recoveryGrid').innerHTML = events.map(e => `
    <article class="small-card">
      <div class="card-top"><h3>${pretty(e.recommended_action)}</h3><span class="action-pill">${esc(e.lifecycle_status || e.action_status || 'DETECTED')}</span></div>
      <div class="big-number">${currency(e.amount)}</div>
      <p><strong>${esc(e.customer)}</strong> · ${pretty(e.event_type)}</p>
      <p>${esc(e.action_reason)}</p>
      ${e.recovery_link_url ? `<div class="reason-box"><strong>Recovery link</strong><br><a href="${esc(e.recovery_link_url)}" target="_blank" rel="noopener" class="text-cyan-300 underline">Open payment link</a>${e.recovered ? '' : `<br><button class="action-btn" style="margin-top:8px" onclick="syncPaymentLink('${esc(e.id)}')">Sync payment</button>`}</div>` : ''}
      ${e.recovered_amount ? `<div class="reason-box"><strong>Recovered</strong><br>${currency(e.recovered_amount)} · ${esc(e.outcome_source || 'confirmed')}</div>` : ''}
      <div class="button-row">
        <button class="action-btn" onclick="executeEvent('${esc(e.id)}')">Execute</button>
        ${e.customer_email ? `<button class="action-btn" onclick="sendRecoveryEmail('${esc(e.id)}','${esc(e.customer_email)}')">Send email</button>` : ''}
        ${!e.recovered && !['do_nothing','escalate'].includes(e.recommended_action) ? `<button class="action-btn success-btn" onclick="confirmRecovered('${esc(e.id)}')">Mark recovered</button>` : ''}
      </div>
    </article>`).join('') || '<div class="empty-state">No recovery actions yet.</div>';
}

async function loadAudit() {
  try {
    const out = await request('/audit?limit=30');
    latestAudit = out.logs || [];
    $('#auditOverviewBody').innerHTML = latestAudit.map(l => `
      <tr><td>${new Date(l.created_at).toLocaleString()}</td><td>${pretty(l.event_id || 'system')}</td><td>${pretty(l.action || l.event_type || '')}</td><td>${pretty(l.status || '')}</td><td>${esc(l.message || '')}</td></tr>`).join('');
    $('#auditOverviewEmpty').classList.toggle('hidden', latestAudit.length > 0);
  } catch (e) { $('#auditOverviewBody').innerHTML=''; $('#auditOverviewEmpty').textContent='Audit unavailable: '+e.message; $('#auditOverviewEmpty').classList.remove('hidden'); }
}

function updateMetricDetails(m, events) {
  const active = events.filter(e => !e.recovered);
  const recovered = events.filter(e => e.recovered);
  const topRisk = active.reduce((acc,e)=>acc+(e.amount||0),0);
  const recoverable = active.reduce((acc,e)=>acc+((e.amount||0)*(e.recovery_probability||0)),0);
  const recoveryRate = (m.recovered && (m.recovered + topRisk)) ? (m.recovered / (m.recovered + topRisk)) : 0;
  $('#riskMetricDetail').textContent = `${active.length} active leak${active.length===1?'':'s'} · ${currency(topRisk)} open exposure`;
  $('#expectedMetricDetail').textContent = `${pct(topRisk ? recoverable / topRisk : 0)} weighted recovery rate · ${active.length} opportunities`;
  $('#recoveredMetricDetail').textContent = recovered.length ? `${recovered.length} recovered event${recovered.length===1?'':'s'} · ${pct(recoveryRate)} of tracked value` : 'No confirmed recoveries yet.';
}

function toggleMetricCard(card) {
  document.querySelectorAll('.metric-button').forEach(c => { if (c !== card) c.classList.remove('expanded'); });
  card.classList.toggle('expanded');
}

async function refresh() {
  try {
    const data = await request('/dashboard');
    latestEvents = data.events || [];
    const m = data.metrics || {};
    $('#riskMetric').textContent = currency(m.revenue_at_risk);
    $('#expectedMetric').textContent = currency(m.expected_recovery);
    $('#recoveredMetric').textContent = currency(m.recovered);
    $('#activeMetric').textContent = m.active_actions ?? 0;
    updateMetricDetails(m, latestEvents);
    renderEventRows(latestEvents); renderRisk(latestEvents); renderRecovery(latestEvents); await loadAudit();
    await refreshHealth();
  } catch (e) {
    $('#eventEmpty').textContent = 'Backend unavailable. Start FastAPI on port 8000.';
    $('#eventEmpty').classList.remove('hidden');
    await refreshHealth();
  }
}

async function refreshHealth() {
  try {
    const h = await fetch(`${API}/health`).then(r=>r.json());
    $('#healthDot').className = `w-2.5 h-2.5 rounded-full ${h.ok ? 'bg-success-emerald' : 'bg-red-500'}`;
    $('#healthText').textContent = h.ok ? `${h.environment || 'development'} API online` : 'API offline';
    $('#razorpayStatus').textContent = 'Optional'; $('#payuStatus').textContent = 'Configure in Settings';
  } catch { $('#healthText').textContent='API offline'; $('#healthDot').className='w-2.5 h-2.5 rounded-full bg-red-500'; $('#razorpayStatus').textContent='Backend offline'; }
}

function showDecision(out) {
  $('#agentEmpty').classList.add('hidden');
  $('#agentDecision').classList.remove('hidden');
  $('#agentDecision').innerHTML = `
    <div class="decision-kicker">${out.recovered ? 'RECOVERY CONFIRMED' : 'ACTION RESULT'}</div>
    <div class="decision-action">${pretty(out.action)}</div>
    <div class="decision-meta"><div class="mini-stat"><span>Amount</span><strong>${currency(out.amount)}</strong></div><div class="mini-stat"><span>Status</span><strong>${out.recovered ? 'Recovered' : esc(out.status || 'ready')}</strong></div></div>
    ${out.lifecycle_status ? `<div class="reason-box"><strong>Lifecycle</strong><br>${esc(out.lifecycle_status)}</div>` : ''}
    ${out.reference ? `<div class="reason-box"><strong>Reference</strong><br>${esc(out.reference)}</div>` : ''}
    <div class="reason-box">${esc(out.message || '')}</div>`;
}
function showError(message){ showDecision({action:'error',status:'failed',amount:0,recovered:false,message}); }

async function executeEvent(id){ try{ const out=await request(`/events/${encodeURIComponent(id)}/execute`,{method:'POST'}); showDecision(out); await refresh(); }catch(e){showError(e.message)} }
window.executeEvent=executeEvent;
async function confirmRecovered(id){ try{ const out=await request(`/events/${encodeURIComponent(id)}/confirm-recovered`,{method:'POST'}); showDecision({action:'recovery_confirmed',status:out.status,amount:out.amount,recovered:true,message:'Demo recovery recorded.'}); await refresh(); }catch(e){showError(e.message)} }
window.confirmRecovered=confirmRecovered;
async function syncPaymentLink(id){ try{ const out=await request(`/events/${encodeURIComponent(id)}/sync-payment-link`,{method:'POST'}); showDecision({action:'payment_link_sync',status:out.status,lifecycle_status:out.recovered?'RECOVERED':'AWAITING_OUTCOME',amount:out.recovered_amount||0,recovered:out.recovered,message:out.recovered?`${String(out.gateway||'Gateway').toUpperCase()} confirms the payment link was paid.`:`${String(out.gateway||'Gateway').toUpperCase()} payment link status: ${out.status}`}); await refresh(); }catch(e){showError(e.message)} }
window.syncPaymentLink=syncPaymentLink;
async function sendRecoveryEmail(id, recipient){ try{ const preview=await request(`/events/${encodeURIComponent(id)}/email-preview`); if(!window.confirm(`Send recovery email to ${recipient}?\n\nSubject: ${preview.subject}`)) return; const out=await request('/recovery/email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:id,recipient,consent:true})}); showDecision({action:'send_recovery_email',status:'sent',amount:0,recovered:false,message:`Recovery email sent to ${out.recipient}${out.mocked?' (demo mode)':''}.`}); await refresh(); }catch(e){showError(e.message)} }
window.sendRecoveryEmail=sendRecoveryEmail;

function openModal(){ $('#modal').classList.remove('hidden'); }
function closeModal(){ $('#modal').classList.add('hidden'); }
$('#simulateBtn').addEventListener('click',openModal); $('#closeModal').addEventListener('click',closeModal);
$('#createEventBtn').addEventListener('click', async ()=>{
  const type=$('#eventType').value;
  const payload={event_type:type,customer:$('#customer').value.trim()||'Demo Customer',amount:Number($('#amount').value),currency:'INR',source:'simulator',failure_reason:type==='payment_failed'?$('#failureReason').value:null,days_overdue:type==='invoice_overdue'?Number($('#daysOverdue').value):0,previous_success_rate:Number($('#successRate').value),prior_contacts:Number($('#priorContacts').value),customer_value:Number($('#amount').value)*4,days_since_last_success:20,event_age_hours:type==='checkout_abandoned'?3:2,is_subscription:type==='payment_failed',customer_email:$('#customerEmail').value.trim(),consent_to_email:true};
  try{ const out=await request('/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); showDecision({...out,action:out.recommended_action,status:'recommended',amount:out.amount,recovered:false,message:out.action_reason}); closeModal(); await refresh(); }catch(e){showError(e.message)}
});

$('#resetBtn').addEventListener('click',async()=>{if(!confirm('Reset demo data for this merchant?'))return;try{await request('/reset',{method:'POST'});showDecision({action:'reset_demo',status:'ready',amount:0,recovered:false,message:'Demo data restored.'});await refresh()}catch(e){showError(e.message)}});

$('#simulateCheckoutBtn').addEventListener('click',async()=>{const session=`demo_${Date.now()}`;try{await request('/checkout/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:session,customer:'Checkout Demo',amount:24999,currency:'INR',stage:'started'})});const out=await request('/checkouts/scan?older_than_hours=0',{method:'POST'});$('#checkoutResult').textContent=`Created ${out.count} abandoned checkout event(s).`;showDecision({action:'checkout_abandonment_scan',status:'detected',amount:24999,recovered:false,message:`Detected ${out.count} abandoned checkout event(s).`});await refresh()}catch(e){$('#checkoutResult').textContent=e.message}}
);

$('#testRazorpayBtn').addEventListener('click',async()=>{try{$('#razorpayTestResult').textContent='Testing…';const out=await request('/integrations/razorpay/test-merchant');$('#razorpayTestResult').textContent=out.ok?`Razorpay ${String(out.mode||'test').toUpperCase()} API connection verified.`:(out.message||'Connection failed')}catch(e){$('#razorpayTestResult').textContent=e.message}});
$('#uploadInvoiceBtn').addEventListener('click',async()=>{const file=$('#invoiceFile').files[0];if(!file){$('#uploadResult').textContent='Choose a CSV first.';return}const form=new FormData();form.append('file',file);try{const out=await request('/invoices/import',{method:'POST',body:form});$('#uploadResult').textContent=`Imported ${out.count} overdue invoice(s).`;await refresh()}catch(e){$('#uploadResult').textContent=e.message}});

// auth
function setAuthError(msg){$('#authError').textContent=msg||''}
function setAuthTab(signup){$('#loginTab').classList.toggle('active',!signup);$('#signupTab').classList.toggle('active',signup);$('#loginForm').classList.toggle('hidden',signup);$('#signupForm').classList.toggle('hidden',!signup);setAuthError('')}
function showAuth(show=true){$('#authOverlay').classList.toggle('hidden',!show)}
function applyMerchant(m){if(!m)return;$('#merchantBusiness').textContent=m.business_name||'Merchant';$('#merchantSender').textContent=`Recovery email: ${m.sender_email||'not set'}`;$('#merchantAvatar').textContent=(m.business_name||'M')[0].toUpperCase();$('#accountMenuBusiness').textContent=m.business_name||'Merchant';$('#accountMenuLogin').textContent=m.login_email||'—';$('#accountMenuSender').textContent=m.sender_email||'not set';$('#accountMenuGateway').textContent=`${m.payment_gateway==='razorpay'?'Razorpay':'PayU'} · ${(m.payment_gateway==='razorpay'?m.razorpay_mode:m.payu_mode)||'test'}`;$('#settingsBusiness').value=m.business_name||'';$('#settingsLoginEmail').value=m.login_email||'';$('#settingsSenderEmail').value=m.sender_email||'';$('#settingsEmailMode').value=m.use_demo_email?'demo':'smtp';$('#emailModeStatus').textContent=m.use_demo_email?'Demo':'SMTP';$('#settingsSmtpFields').classList.toggle('hidden',m.use_demo_email);if(m.smtp_host)$('#settingsSmtpHost').value=m.smtp_host;if(m.smtp_port)$('#settingsSmtpPort').value=m.smtp_port;if(m.smtp_username)$('#settingsSmtpUser').value=m.smtp_username;$('#payuMode').value=m.payu_mode||'test';$('#payuMerchantId').value=m.payu_merchant_id||'';$('#payuWebhookUrl').textContent=m.payu_webhook_url||'Not configured';$('#merchantPayUStatus').textContent=m.payu_configured?`${(m.payu_mode||'test').toUpperCase()} connected`:'Not connected';$('#merchantPayUStatus').className=`status-pill ${m.payu_configured?'good-status':''}`;$('#rzpMode').value=m.razorpay_mode||'test';$('#rzpKeyId').value=m.razorpay_key_id||'';$('#rzpWebhookUrl').textContent=m.razorpay_webhook_url||'Not configured';$('#merchantRazorpayStatus').textContent=m.razorpay_configured?`${(m.razorpay_mode||'test').toUpperCase()} connected`:'Optional';}
async function authenticate(){if(!getToken()){showAuth(true);return false}try{const me=await request('/auth/me');applyMerchant(me);showAuth(false);return true}catch{setToken('');showAuth(true);return false}}
$('#loginTab').addEventListener('click',()=>setAuthTab(false));$('#signupTab').addEventListener('click',()=>setAuthTab(true));$('#signupDemoMode').addEventListener('change',e=>$('#signupSmtp').classList.toggle('hidden',e.target.checked));$('#settingsEmailMode').addEventListener('change',e=>{$('#settingsSmtpFields').classList.toggle('hidden',e.target.value==='demo');$('#emailModeStatus').textContent=e.target.value==='demo'?'Demo':'SMTP'});
$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();try{const out=await fetch(`${API}/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login_email:$('#loginEmail').value.trim(),password:$('#loginPassword').value})}).then(async r=>{const d=await r.json();if(!r.ok)throw new Error(d.detail||'Login failed');return d});setToken(out.token);applyMerchant(out.merchant);showAuth(false);await refresh()}catch(e){setAuthError(e.message)}});
$('#signupForm').addEventListener('submit',async e=>{e.preventDefault();const demo=$('#signupDemoMode').checked;try{const out=await fetch(`${API}/auth/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({business_name:$('#signupBusiness').value.trim(),login_email:$('#signupEmail').value.trim(),password:$('#signupPassword').value,sender_email:$('#signupSender').value.trim(),use_demo_email:demo,smtp_host:demo?null:$('#signupSmtpHost').value.trim()||null,smtp_port:Number($('#signupSmtpPort').value)||587,smtp_username:demo?null:$('#signupSmtpUser').value.trim()||null,smtp_password:demo?null:$('#signupSmtpPassword').value||null})}).then(async r=>{const d=await r.json();if(!r.ok)throw new Error(d.detail||'Registration failed');return d});setToken(out.token);applyMerchant(out.merchant);showAuth(false);await refresh()}catch(e){setAuthError(e.message)}});
$('#logoutBtn').addEventListener('click',()=>{setToken('');showAuth(true)});

// settings connectors
$('#saveEmailSettingsBtn').addEventListener('click',async()=>{const demo=$('#settingsEmailMode').value==='demo';try{await request('/auth/email-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({sender_email:$('#settingsSenderEmail').value.trim(),use_demo_email:demo,smtp_host:demo?null:$('#settingsSmtpHost').value.trim()||null,smtp_port:Number($('#settingsSmtpPort').value)||587,smtp_username:demo?null:$('#settingsSmtpUser').value.trim()||null,smtp_password:demo?null:$('#settingsSmtpPassword').value||null})});applyMerchant(await request('/auth/me'));$('#settingsResult').textContent='Email settings saved.'}catch(e){$('#settingsResult').textContent=e.message}});
$('#testEmailBtn').addEventListener('click',async()=>{const recipient=$('#testEmailRecipient').value.trim();if(!recipient){$('#settingsResult').textContent='Enter a test recipient.';return}try{const out=await request('/auth/email-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient})});$('#settingsResult').textContent=`${out.message} Sender: ${out.sender}`;await loadAudit()}catch(e){$('#settingsResult').textContent=e.message}});
$('#rzpMode').addEventListener('change',e=>$('#rzpKeyId').placeholder=e.target.value==='live'?'rzp_live_...':'rzp_test_...');

$('#savePayUBtn').addEventListener('click',async()=>{try{const mode=$('#payuMode').value,merchant_id=$('#payuMerchantId').value.trim(),client_id=$('#payuClientId').value.trim(),client_secret=$('#payuClientSecret').value,key=$('#payuKey').value.trim(),salt=$('#payuSalt').value;if(!merchant_id||!client_id||!client_secret)throw new Error('Enter PayU Merchant ID, Client ID and Client Secret.');const out=await request('/integrations/payu/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({merchant_id,client_id,client_secret,key,salt,mode})});$('#payuMerchantResult').textContent=`Saved ${mode.toUpperCase()} PayU connection. Webhook URL: ${out.webhook_url}`;applyMerchant(await request('/auth/me'));}catch(e){$('#payuMerchantResult').textContent=e.message}});
$('#testPayUMerchantBtn').addEventListener('click',async()=>{try{$('#payuMerchantResult').textContent='Testing PayU API…';const out=await request('/integrations/payu/test-merchant');$('#payuMerchantResult').textContent=out.ok?`PayU ${String(out.mode||'test').toUpperCase()} API connection verified.`:(out.message||'Connection failed')}catch(e){$('#payuMerchantResult').textContent=e.message}});
$('#testPayUBtn').addEventListener('click',async()=>{try{$('#payuTestResult').textContent='Testing PayU API…';const out=await request('/integrations/payu/test-merchant');$('#payuTestResult').textContent=out.ok?`PayU ${String(out.mode||'test').toUpperCase()} API connection verified.`:(out.message||'Connection failed')}catch(e){$('#payuTestResult').textContent=e.message}});
$('#saveRazorpayBtn').addEventListener('click',async()=>{try{const mode=$('#rzpMode').value,key_id=$('#rzpKeyId').value.trim(),key_secret=$('#rzpKeySecret').value,webhook_secret=$('#rzpWebhookSecret').value;if(!key_id||!key_secret||!webhook_secret)throw new Error('Enter Key ID, Key Secret and Webhook Secret.');const out=await request('/integrations/razorpay/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({key_id,key_secret,webhook_secret,mode})});$('#razorpayMerchantResult').textContent=`Saved ${mode.toUpperCase()} connection. Webhook URL: ${out.webhook_url}`;applyMerchant(await request('/auth/me'));await refreshHealth()}catch(e){$('#razorpayMerchantResult').textContent=e.message}});
$('#testRazorpayMerchantBtn').addEventListener('click',async()=>{try{$('#razorpayMerchantResult').textContent='Testing Razorpay API…';const out=await request('/integrations/razorpay/test-merchant');$('#razorpayMerchantResult').textContent=out.ok?`Razorpay ${String(out.mode||'test').toUpperCase()} API connection verified.`:(out.message||'Connection failed')}catch(e){$('#razorpayMerchantResult').textContent=e.message}});

document.querySelectorAll('.metric-button').forEach(card => card.addEventListener('click', ()=>toggleMetricCard(card)));
$('#accountButton')?.addEventListener('click',()=>{ const menu=$('#accountMenu'); const open=menu.classList.toggle('hidden'); $('#accountButton').setAttribute('aria-expanded', String(!open)); });
document.addEventListener('click', e=>{ if(!e.target.closest('.account-menu-wrap')) { $('#accountMenu')?.classList.add('hidden'); $('#accountButton')?.setAttribute('aria-expanded','false'); } });
$('#accountSettingsBtn')?.addEventListener('click',()=>{ $('#accountMenu')?.classList.add('hidden'); showView('settings'); });
$('#refreshAuditBtn')?.addEventListener('click', loadAudit);
(async()=>{if(await authenticate())await refresh()})();
