(() => {
  if (window.__orderankuAndroidFixInstalled) return;
  window.__orderankuAndroidFixInstalled = true;

  let lastOpenAt = 0;
  let lastIndex = -1;

  function openFromTarget(target, event) {
    const button = target?.closest?.('#myOrdersList .order-area-button[data-area-index]');
    if (!button) return false;

    const index = Number(button.dataset.areaIndex);
    const areas = (typeof state !== 'undefined' ? state.myOpenOrders?.areas : window.state?.myOpenOrders?.areas) || [];
    const area = areas[index];
    if (!area || typeof window.renderMyOpenArea !== 'function') return false;

    const now = Date.now();
    if (index === lastIndex && now - lastOpenAt < 700) {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      return true;
    }

    lastIndex = index;
    lastOpenAt = now;
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

  document.addEventListener('pointerup', event => {
    if (event.pointerType === 'mouse') return;
    openFromTarget(event.target, event);
  }, true);

  document.addEventListener('touchend', event => {
    openFromTarget(event.target, event);
  }, { capture: true, passive: false });

  document.addEventListener('click', event => {
    openFromTarget(event.target, event);
  }, true);
})();
