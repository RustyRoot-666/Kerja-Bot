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

    // Result -> return to the selected order/form context.
    if (document.querySelector('#wfOutputs')) {
      const order = state.workflow?.order;
      if (action && order) renderWorkflowForm(action, order);
      else if (action) startWorkflow(action);
      else renderWorkflowHome();
      return;
    }

    // Form -> return to INET list for the same area.
    if (document.querySelector('#wfForm')) {
      const area = currentWorkflowArea();
      if (action && area) renderWorkflowAreaOrders(action, area);
      else if (action) renderWorkflowAreas(action, state.myOpenOrders);
      else renderWorkflowHome();
      return;
    }

    // INET list -> return to area list.
    if (document.querySelector('#wfOrders')) {
      if (action) renderWorkflowAreas(action, state.myOpenOrders);
      else renderWorkflowHome();
      return;
    }

    // Area list -> return to workflow selector.
    if (document.querySelector('#wfAreaList')) {
      renderWorkflowHome();
      return;
    }

    // Workflow selector -> dashboard.
    openPage('dashboardPage');
    return;
  }

  if (page.id === 'ordersPage') {
    // If Orderanku is showing one area's orders, back returns to area list first.
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

// Existing app.js binds header arrows straight to dashboard. Intercept first.
document.querySelectorAll('[data-back-dashboard]').forEach(button => {
  button.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    smartBack();
  }, true);
});

// Keep Telegram's native Mini App back button consistent when available.
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
