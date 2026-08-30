(() => {
  if (window.__orderankuAndroidFixInstalled) return;
  window.__orderankuAndroidFixInstalled = true;

  const getAreas = () => {
    try {
      return (typeof state !== 'undefined' ? state.myOpenOrders?.areas : window.state?.myOpenOrders?.areas) || [];
    } catch (_) {
      return window.state?.myOpenOrders?.areas || [];
    }
  };

  function openAreaByButton(button, event) {
    if (!button) return false;
    const index = Number(button.dataset.areaIndex);
    const area = getAreas()[index];
    if (!area || typeof window.renderMyOpenArea !== 'function') return false;

    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      window.renderMyOpenArea(area);
      window.scrollTo({ top: 0, behavior: 'auto' });
      return true;
    } catch (error) {
      console.error('Orderanku area navigation failed', error);
      window.showToast?.('Gagal membuka area. Coba refresh.');
      return false;
    }
  }

  function bindButtons() {
    document.querySelectorAll('#myOrdersList .order-area-button[data-area-index]').forEach(button => {
      if (button.dataset.androidBound === '1') return;
      button.dataset.androidBound = '1';

      // Property handlers are intentional here: Telegram Android WebView has shown
      // cases where delegated click listeners do not reliably fire after DOM replacement.
      button.onclick = event => openAreaByButton(button, event);
      button.ontouchend = event => openAreaByButton(button, event);
      button.onpointerup = event => {
        if (event.pointerType !== 'mouse') openAreaByButton(button, event);
      };
    });
  }

  const list = document.querySelector('#myOrdersList');
  if (list) {
    new MutationObserver(() => bindButtons()).observe(list, { childList: true, subtree: true });
  }

  const originalRenderAreas = window.renderMyOrderAreas;
  if (typeof originalRenderAreas === 'function' && !originalRenderAreas.__directTouchBound) {
    const wrapped = function(...args) {
      const result = originalRenderAreas.apply(this, args);
      queueMicrotask(bindButtons);
      return result;
    };
    wrapped.__directTouchBound = true;
    window.renderMyOrderAreas = wrapped;
  }

  bindButtons();
})();
