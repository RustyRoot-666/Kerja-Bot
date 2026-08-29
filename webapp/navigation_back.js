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

  if (page.id !== 'dashboardPage') {
    openPage('dashboardPage');
  }
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

// Load richer personal report first, then attach CONFIG/REPORT/STO history editor.
(() => {
  if (document.querySelector('script[data-report-dashboard]')) return;
  const script = document.createElement('script');
  script.src = `/report_dashboard.js?v=${Date.now()}`;
  script.dataset.reportDashboard = '1';
  script.onload = () => {
    if (document.querySelector('script[data-report-history-editor]')) return;
    const history = document.createElement('script');
    history.src = `/report_history_editor.js?v=${Date.now()}`;
    history.dataset.reportHistoryEditor = '1';
    document.body.appendChild(history);
  };
  document.body.appendChild(script);
})();

// Normalize technician identities after the core dashboard bundle is ready.
(() => {
  if (document.querySelector('script[data-leaderboard-identity-fix]')) return;
  const script = document.createElement('script');
  script.src = `/leaderboard_identity_fix.js?v=${Date.now()}`;
  script.dataset.leaderboardIdentityFix = '1';
  document.body.appendChild(script);
})();

// Load persistent workflow history so unfinished input survives Mini App close.
(() => {
  if (document.querySelector('script[data-draft-history]')) return;
  const script = document.createElement('script');
  script.src = `/draft_history.js?v=${Date.now()}`;
  script.dataset.draftHistory = '1';
  document.body.appendChild(script);
})();

// Generated CONFIG/REPORT/STO are editable code blocks; technician copies CODE,
// not a decorative message card.
(() => {
  if (document.querySelector('script[data-input-code-editor]')) return;
  const script = document.createElement('script');
  script.src = `/input_code_editor.js?v=${Date.now()}`;
  script.dataset.inputCodeEditor = '1';
  document.body.appendChild(script);
})();

// Make Orderanku entries interactive: tap an OPEN order to inspect full Sheet
// information, copy customer WhatsApp format, or continue directly to Input.
(() => {
  if (document.querySelector('script[data-order-detail]')) return;
  const script = document.createElement('script');
  script.src = `/order_detail.js?v=${Date.now()}`;
  script.dataset.orderDetail = '1';
  document.body.appendChild(script);
})();
