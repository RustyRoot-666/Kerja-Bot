// Persistent Mini App input history.
// Drafts are stored in the bot SQLite database so unfinished work can be resumed
// after closing Telegram or switching devices.

const draftState = { items: [], timer: null };

function draftTelegramId() {
  return String(telegramUser()?.id || '').trim();
}

function draftKey(action, service) {
  return `${String(action || '').toLowerCase()}:${String(service || '').trim()}`;
}

async function loadDraftHistory() {
  const telegramId = draftTelegramId();
  if (!telegramId) return [];
  try {
    const response = await fetch(`/api/workflow-drafts?${new URLSearchParams({ telegram_id: telegramId })}`, { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
    draftState.items = payload.items || [];
    return draftState.items;
  } catch (error) {
    console.error('Gagal membaca history input', error);
    draftState.items = [];
    return [];
  }
}

function findDraft(action, service) {
  const key = draftKey(action, service);
  return draftState.items.find(item => draftKey(item.action, item.service_number) === key) || null;
}

async function saveDraft(action, order, data, status = 'draft') {
  const telegramId = draftTelegramId();
  if (!telegramId || !order?.service_number) return;
  const payload = {
    telegram_id: telegramId,
    action,
    service_number: order.service_number,
    order,
    data,
    status,
  };
  try {
    const response = await fetch('/api/workflow-drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
    const item = { ...payload, updated_at: result.updated_at };
    const key = draftKey(action, order.service_number);
    draftState.items = [item, ...draftState.items.filter(row => draftKey(row.action, row.service_number) !== key)].slice(0, 30);
  } catch (error) {
    console.error('Gagal menyimpan history input', error);
  }
}

async function deleteDraft(action, service) {
  const telegramId = draftTelegramId();
  if (!telegramId) return;
  try {
    const params = new URLSearchParams({ telegram_id: telegramId, action, service_number: service });
    const response = await fetch(`/api/workflow-drafts?${params}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const key = draftKey(action, service);
    draftState.items = draftState.items.filter(item => draftKey(item.action, item.service_number) !== key);
    renderWorkflowHome();
    showToast('History input dihapus');
  } catch (error) {
    console.error('Gagal menghapus history input', error);
    showToast('Gagal menghapus history');
  }
}

function draftDateLabel(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

function historyMarkup(items) {
  if (!items.length) return '';
  const rows = items.slice(0, 10).map((item, index) => {
    const order = item.order || {};
    const status = item.status === 'completed' ? '✅ SELESAI' : '🟡 BELUM SELESAI';
    return `<div class="mini-order" style="margin-top:8px">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div style="min-width:0;flex:1">
          <strong>${esc(String(item.action || '').toUpperCase())} • ${esc(item.service_number || '-')}</strong>
          <small>${esc(order.customer_name || '-')} • ${esc(order.area || '-')}<br>${status} • ${esc(draftDateLabel(item.updated_at))}</small>
        </div>
        <span style="color:#55d9ff;font-size:10px;white-space:nowrap">${index + 1}</span>
      </div>
      <button class="tool-action" type="button" data-resume-draft="${index}"><b>↻ LANJUTKAN</b><span>Resume ›</span></button>
      <button class="tool-action" type="button" data-delete-draft="${index}" style="border-color:#59313a"><b>Hapus history</b><span>✕</span></button>
    </div>`;
  }).join('');
  return `<article class="tool-card" id="workflowHistoryCard" style="border-color:#37506d">
    <strong>🕘 HISTORY INPUT</strong>
    <small>Proses yang belum selesai disimpan otomatis. Jika VALINS atau data lain belum ada, teknisi dapat melanjutkan lagi tanpa mengulang dari awal.</small>
    <div style="margin-top:8px">${rows}</div>
  </article>`;
}

function bindHistoryButtons() {
  document.querySelectorAll('[data-resume-draft]').forEach(button => {
    button.addEventListener('click', () => {
      const item = draftState.items[Number(button.dataset.resumeDraft)];
      if (!item) return;
      state.workflow = { action: item.action, order: item.order || {} };
      renderWorkflowForm(item.action, { ...(item.order || {}), __draftData: item.data || {} });
      showToast(`Melanjutkan ${String(item.action || '').toUpperCase()} ${item.service_number}`);
    });
  });
  document.querySelectorAll('[data-delete-draft]').forEach(button => {
    button.addEventListener('click', () => {
      const item = draftState.items[Number(button.dataset.deleteDraft)];
      if (item) deleteDraft(item.action, item.service_number);
    });
  });
}

const _renderWorkflowHomeBeforeHistory = renderWorkflowHome;
renderWorkflowHome = function renderWorkflowHomeWithHistory() {
  _renderWorkflowHomeBeforeHistory();
  loadDraftHistory().then(items => {
    const host = workflowHost();
    if (!host || !items.length || document.querySelector('#workflowHistoryCard')) return;
    host.insertAdjacentHTML('afterbegin', historyMarkup(items));
    bindHistoryButtons();
  });
};

const _renderWorkflowFormBeforeHistory = renderWorkflowForm;
renderWorkflowForm = function renderWorkflowFormWithDrafts(action, order) {
  const inlineDraft = order?.__draftData || null;
  const cleanOrder = { ...(order || {}) };
  delete cleanOrder.__draftData;
  _renderWorkflowFormBeforeHistory(action, cleanOrder);

  const baseData = workflowSeed(cleanOrder);
  const draft = inlineDraft || findDraft(action, cleanOrder.service_number)?.data || {};
  const form = document.querySelector('#wfForm');
  if (!form) return;

  Object.entries(draft).forEach(([key, value]) => {
    const input = form.elements.namedItem(key);
    if (input && String(value || '').trim()) input.value = value;
  });

  const snapshot = () => {
    const data = { ...baseData };
    new FormData(form).forEach((value, key) => { data[key] = String(value || '').trim(); });
    return data;
  };

  // Create the draft immediately, even before the technician types anything.
  saveDraft(action, cleanOrder, { ...baseData, ...draft }, 'draft');

  form.addEventListener('input', () => {
    const data = snapshot();
    clearTimeout(draftState.timer);
    draftState.timer = setTimeout(() => saveDraft(action, cleanOrder, data, 'draft'), 350);
  });
  form.addEventListener('change', () => saveDraft(action, cleanOrder, snapshot(), 'draft'));
  form.addEventListener('submit', () => saveDraft(action, cleanOrder, snapshot(), 'completed'));
};
