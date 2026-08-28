// Ticket helper layer for Mini App input workflow.
// Keeps Mini App aligned with chatbot/Sheet ticket priority:
// INSERA TODAY -> TIKET -> MANUAL.

const MINIAPP_EMPTY_TICKETS = new Set(['', '-', 'MANUAL', 'N/A', 'NA', 'NONE']);

function miniappTicket(value) {
  const raw = String(value || '').trim();
  return MINIAPP_EMPTY_TICKETS.has(raw.toUpperCase()) ? 'MANUAL' : raw;
}

function miniappIsManualTicket(value) {
  return miniappTicket(value) === 'MANUAL';
}

// Override the original seed so a missing ticket is represented as MANUAL,
// rather than being treated as another field the technician must type.
workflowSeed = function workflowSeedWithTicketFallback(order) {
  return {
    ticket_id: miniappTicket(order.ticket_id),
    service_number: order.service_number || '',
    customer_name: order.customer_name || '',
    address: order.address || '',
    customer_phone: order.customer_phone || '',
    voip_number: order.voip_number || '',
    old_sn: order.old_sn || '',
    new_sn: order.new_sn || '',
    ont_type: order.ont_type || '',
    sto: order.sto || state.myOpenOrders?.technician?.sto || '',
    valins_id: order.valins_id || '',
    result: order.result || '',
    config_description: order.config_description || '',
    report_description: order.report_description || '',
  };
};

function findFreshOpenOrder(serviceNumber) {
  const target = String(serviceNumber || '').trim();
  for (const area of state.myOpenOrders?.areas || []) {
    for (const order of area.orders || []) {
      if (String(order.service_number || '').trim() === target) {
        return { ...order, area: area.area };
      }
    }
  }
  return null;
}

async function refreshWorkflowTicket(action, serviceNumber) {
  showToast('Mengecek tiket terbaru...');
  try {
    await fetchMyOpenOrders(true);
    const fresh = findFreshOpenOrder(serviceNumber);
    if (!fresh) {
      showToast('Order tidak ditemukan pada Sheet terbaru');
      return;
    }
    state.workflow = { action, order: fresh };
    if (miniappIsManualTicket(fresh.ticket_id)) {
      renderWorkflowForm(action, fresh);
      showToast('Tiket masih MANUAL');
      return;
    }
    renderWorkflowForm(action, fresh);
    showToast(`Tiket ditemukan: ${fresh.ticket_id}`);
  } catch (error) {
    console.error('Gagal refresh tiket Mini App', error);
    showToast('Gagal mengecek tiket terbaru');
  }
}

function ticketHelperMarkup(order) {
  if (!miniappIsManualTicket(order.ticket_id)) {
    return `<div class="info-box" style="margin-top:12px"><span>🎫</span><p><strong style="color:#eef6ff">Tiket: ${esc(order.ticket_id)}</strong><br>Prioritas sumber: INSERA TODAY → TIKET → MANUAL.</p></div>`;
  }
  return `
    <div class="tool-card" style="margin-top:12px;border-color:#6b5425;background:linear-gradient(180deg,#191b20,#101820)">
      <strong>⚠ TIKET MASIH MANUAL</strong>
      <small>INSERA TODAY dan TIKET pada Order Sheet belum berisi tiket. Gunakan helper di bawah, lalu cek ulang Sheet.</small>
      <button class="tool-action" type="button" id="wfReqOpenTicket"><b>🎫 #REQOPENTIKET</b><span>Salin ›</span></button>
      <button class="tool-action" type="button" id="wfInfoTicket"><b>🔎 /infotiket</b><span>Salin ›</span></button>
      <button class="tool-action" type="button" id="wfRefreshTicket"><b>↻ CEK TIKET TERBARU</b><span>Sheet ›</span></button>
    </div>`;
}

function reqOpenTicketText(order) {
  const sto = String(order.sto || state.myOpenOrders?.technician?.sto || '').trim().toUpperCase() || '-';
  const inet = String(order.service_number || '').trim() || '-';
  return `#REQOPENTIKET\nSTO: ${sto}\n\nNOMER INET:\n${inet}\n\nmoban create tiket`;
}

function bindTicketHelpers(action, order) {
  document.querySelector('#wfReqOpenTicket')?.addEventListener('click', async () => {
    await copyText(reqOpenTicketText(order), '#REQOPENTIKET lengkap tersalin');
  });
  document.querySelector('#wfInfoTicket')?.addEventListener('click', async () => {
    await copyText(`/infotiket ${order.service_number}`, '/infotiket tersalin');
  });
  document.querySelector('#wfRefreshTicket')?.addEventListener('click', () => {
    refreshWorkflowTicket(action, order.service_number);
  });
}

// Extend the existing form while retaining exactly the same CONFIG/REPORT/STO
// field requirements and output generator as the normal Mini App workflow.
renderWorkflowForm = function renderWorkflowFormWithTicketTools(action, order) {
  state.workflow = { action, order };
  const data = workflowSeed(order);
  const required = WF_REQUIRED[action];
  const missing = required.filter(k => !String(data[k] || '').trim());
  const host = workflowHost();

  const known = required
    .filter(k => String(data[k] || '').trim())
    .map(k => `<div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid rgba(87,119,153,.13);font-size:10px"><span style="color:#8298b2">${WF_LABELS[k]}</span><strong style="text-align:right">${esc(data[k])}</strong></div>`)
    .join('');

  const fields = missing
    .map(k => `<label style="display:block;margin:11px 0"><span style="display:block;color:#9cb0c5;font-size:10px;margin-bottom:5px">${WF_LABELS[k]}</span><input name="${k}" required placeholder="Isi ${WF_LABELS[k]}${['valins_id','voip_number'].includes(k) ? ' atau -' : ''}" style="width:100%;border:1px solid #2a496b;border-radius:12px;background:#081727;color:#fff;padding:12px;outline:none" /></label>`)
    .join('');

  host.innerHTML = `<article class="tool-card">
    <strong>${action.toUpperCase()} • ${esc(order.service_number)}</strong>
    <small>${esc(order.customer_name || '-')} • ${esc(order.address || '-')}</small>
    ${ticketHelperMarkup(order)}
    ${known ? `<div style="margin-top:12px">${known}</div>` : ''}
    <form id="wfForm" style="margin-top:10px">
      ${fields || '<div class="info-box"><span>✓</span><p>Semua data yang dibutuhkan sudah tersedia.</p></div>'}
      <button class="tool-action" type="submit"><b>BUAT ${action.toUpperCase()}</b><span>Proses ›</span></button>
    </form>
    <button class="tool-action" id="wfBackOrders"><b>‹ Pilih order lain</b><span>🌐</span></button>
  </article>`;

  bindTicketHelpers(action, order);
  document.querySelector('#wfBackOrders').addEventListener('click', () => startWorkflow(action));
  document.querySelector('#wfForm').addEventListener('submit', event => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    missing.forEach(k => {
      data[k] = String(formData.get(k) || '').trim() || '-';
    });
    // Never let an empty/placeholder Sheet ticket disappear from the output.
    data.ticket_id = miniappTicket(data.ticket_id);
    renderWorkflowResult(action, order, data);
  });
};
