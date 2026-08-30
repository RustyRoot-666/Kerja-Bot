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
    const list = document.querySelector('#myOrdersList');
    const areas = getAreas();
    if (!list || !areas.length) return;

    const buttons = [...list.querySelectorAll(':scope > button.tool-action')];

    // Kalau sedang berada di detail area, jangan salah mengikat tombol Kembali
    // sebagai area pertama.
    if (buttons.some(button => /kembali ke daftar area/i.test(button.textContent || ''))) return;

    // renderMyOrderAreas() menghasilkan tepat satu .tool-action per area.
    // app.js lama belum menambahkan class/data-area-index, jadi lengkapi di sini.
    if (buttons.length !== areas.length) return;

    buttons.forEach((button, index) => {
      button.classList.add('order-area-button');
      button.dataset.areaIndex = String(index);

      if (button.dataset.androidBound === '1') return;
      button.dataset.androidBound = '1';

      const activate = event => openAreaByButton(button, event);
      button.onclick = activate;
      button.ontouchend = activate;
      button.onpointerup = event => {
        if (event.pointerType !== 'mouse') activate(event);
      };
    });
  }

  const list = document.querySelector('#myOrdersList');
  if (list) {
    new MutationObserver(() => queueMicrotask(bindButtons)).observe(list, { childList: true, subtree: true });
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
