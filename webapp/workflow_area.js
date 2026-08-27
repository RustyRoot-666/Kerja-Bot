// Area-first workflow navigation for Mini App Input.
// Flow: workflow -> area -> INET -> fill only missing fields.

function renderWorkflowAreas(action, payload) {
  const host = workflowHost();
  const areas = (payload?.areas || []).filter(area => (area.orders || []).length);
  host.innerHTML = `<article class="tool-card">
    <strong>${action.toUpperCase()} • PILIH AREA</strong>
    <small>Pilih area seperti /orderanku, lalu pilih INET yang akan dikerjakan.</small>
    <div id="wfAreaList" class="mini-order-list" style="margin-top:10px"></div>
    <button class="tool-action" id="wfBackHome"><b>‹ Ganti workflow</b><span>${action.toUpperCase()}</span></button>
  </article>`;

  const list = document.querySelector('#wfAreaList');
  if (!areas.length) {
    list.innerHTML = '<div class="empty"><p>✅ Tidak ada order OPEN.</p></div>';
  } else {
    areas.forEach(area => {
      const button = document.createElement('button');
      button.className = 'tool-action';
      button.innerHTML = `<div><b>📍 ${esc(area.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${fmt(area.open || (area.orders || []).length)} | 🔴 Close: ${fmt(area.close || 0)}${area.update ? ` | 🟡 Update: ${fmt(area.update)}` : ''}</small></div><span>${fmt((area.orders || []).length)} ›</span>`;
      button.addEventListener('click', () => renderWorkflowAreaOrders(action, area));
      list.appendChild(button);
    });
  }
  document.querySelector('#wfBackHome')?.addEventListener('click', renderWorkflowHome);
}

function renderWorkflowAreaOrders(action, area) {
  const rows = (area.orders || []).map(order => ({ ...order, area: area.area }));
  renderWorkflowOrders(action, rows);
  const card = workflowHost().querySelector('.tool-card');
  if (!card) return;

  const heading = card.querySelector('strong');
  if (heading) heading.textContent = `${action.toUpperCase()} • ${area.area}`;
  const small = card.querySelector('small');
  if (small) small.textContent = `${rows.length} order OPEN • pilih INET yang akan dikerjakan`;

  const back = card.querySelector('#wfBack');
  if (back) {
    back.innerHTML = `<b>‹ Kembali ke area</b><span>📍 ${esc(area.area)}</span>`;
    back.replaceWith(back.cloneNode(true));
    card.querySelector('#wfBack')?.addEventListener('click', () => renderWorkflowAreas(action, state.myOpenOrders));
  }
}

// Replace the previous direct workflow -> INET jump.
startWorkflow = async function startWorkflowAreaFirst(action) {
  state.workflow = { action, order: null };
  const host = workflowHost();
  host.innerHTML = '<div class="empty"><p>🔄 Membaca order OPEN dari Google Sheet...</p></div>';
  try {
    const payload = state.myOpenOrders || await fetchMyOpenOrders(false);
    renderWorkflowAreas(action, payload);
  } catch (error) {
    host.innerHTML = `<div class="empty"><p>❌ ${esc(error.message)}</p><button class="tool-action" id="wfBack"><b>Kembali</b><span>‹</span></button></div>`;
    document.querySelector('#wfBack')?.addEventListener('click', renderWorkflowHome);
  }
};

// ticket_bridge.js owns the final form renderer. Wrap it to show operational
// Sheet context such as ONU RX without turning ONU RX into a required field.
const _renderWorkflowFormWithTicket = renderWorkflowForm;
renderWorkflowForm = function renderWorkflowFormWithAreaContext(action, order) {
  _renderWorkflowFormWithTicket(action, order);
  const article = workflowHost()?.querySelector('.tool-card');
  if (!article) return;

  const ticketBlock = article.querySelector('.info-box, .tool-card');
  const context = document.createElement('div');
  context.className = 'info-box';
  context.style.marginTop = '12px';
  context.innerHTML = `<span>📡</span><p><strong style="color:#eef6ff">Data jaringan dari Sheet</strong><br>ONU RX: <b>${esc(order.onu_rx || '-')}</b>${order.package ? ` • Paket: <b>${esc(order.package)}</b>` : ''}${order.rca ? ` • RCA: <b>${esc(order.rca)}</b>` : ''}</p>`;

  if (ticketBlock?.parentNode === article) ticketBlock.insertAdjacentElement('afterend', context);
  else article.insertBefore(context, article.querySelector('form'));
};
