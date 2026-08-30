// Context-aware back navigation for Kerja BOT Mini App.
// Header back should step out of the current workflow before returning home.

function currentVisiblePage() {
  return [...document.querySelectorAll('.page-view')].find(page => !page.classList.contains('hidden')) || null;
}

function currentWorkflowArea() {
  const areaName = state.workflow?.order?.area;
  if (!areaName) return null;
  return (state.myOpenOrders?.areas || []).find(area => area.area === areaName) || null;
}

function smartBack() {
  const page = currentVisiblePage();
  if (!page) return;

  if (page.id === 'inputPage') {
    const action = state.workflow?.action;

    if (document.querySelector('#wfOutputs')) {
      const order = state.workflow?.order;
      if (action && order) renderWorkflowForm(action, order);
      else if (action) startWorkflow(action);
      else renderWorkflowHome();
      return;
    }

    if (document.querySelector('#wfForm')) {
      const area = currentWorkflowArea();
      if (action && area) renderWorkflowAreaOrders(action, area);
      else if (action) renderWorkflowAreas(action, state.myOpenOrders);
      else renderWorkflowHome();
      return;
    }

    if (document.querySelector('#wfOrders')) {
      if (action) renderWorkflowAreas(action, state.myOpenOrders);
      else renderWorkflowHome();
      return;
    }

    if (document.querySelector('#wfAreaList')) {
      renderWorkflowHome();
      return;
    }

    openPage('dashboardPage');
    return;
  }

  if (page.id === 'ordersPage') {
    const areaBack = [...document.querySelectorAll('#myOrdersList .tool-action')]
      .find(button => button.textContent.includes('Kembali ke daftar area'));
    if (areaBack) {
      renderMyOrderAreas(state.myOpenOrders);
      return;
    }
  }

  if (page.id !== 'dashboardPage') openPage('dashboardPage');
}

document.querySelectorAll('[data-back-dashboard]').forEach(button => {
  button.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    smartBack();
  }, true);
});

if (tg?.BackButton) {
  const syncTelegramBack = () => {
    const page = currentVisiblePage();
    if (page && page.id !== 'dashboardPage') tg.BackButton.show();
    else tg.BackButton.hide();
  };
  tg.BackButton.onClick(smartBack);

  const originalOpenPage = openPage;
  openPage = function openPageWithBackSync(id) {
    originalOpenPage(id);
    syncTelegramBack();
  };
  syncTelegramBack();
}

function loadMiniAppScript(src, marker) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-${marker}]`);
    if (existing) {
      if (existing.dataset.loaded === '1') resolve();
      else {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
      }
      return;
    }
    const script = document.createElement('script');
    script.src = `${src}?v=20260830-orderfix1`;
    script.dataset[marker.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = '1';
    script.onload = () => {
      script.dataset.loaded = '1';
      resolve();
    };
    script.onerror = reject;
    document.body.appendChild(script);
  });
}

loadMiniAppScript('/report_dashboard.js', 'report-dashboard')
  .then(() => loadMiniAppScript('/report_history_editor.js', 'report-history-editor'))
  .catch(error => console.error('Gagal memuat report enhancement', error));

loadMiniAppScript('/leaderboard_identity_fix.js', 'leaderboard-identity-fix')
  .catch(error => console.error('Gagal memuat identity fix', error));

loadMiniAppScript('/draft_history.js', 'draft-history')
  .then(() => loadMiniAppScript('/input_code_editor.js', 'input-code-editor'))
  .catch(error => console.error('Gagal memuat workflow enhancement', error));

loadMiniAppScript('/order_detail.js', 'order-detail')
  .then(() => loadMiniAppScript('/manja_ui.js', 'manja-ui'))
  .catch(error => console.error('Gagal memuat detail order/MANJA', error));

loadMiniAppScript('/interactive_ui.js', 'interactive-ui')
  .catch(error => console.error('Gagal memuat interaction enhancement', error));
