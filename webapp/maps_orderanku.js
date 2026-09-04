// Google Maps integration for Mini App Orderanku.
// Adds a Maps button to every rendered order without changing the order data/API.

(function () {
  function mapsUrl(address) {
    const value = String(address || '').trim();
    if (!value || value === '-') return '';
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(value)}`;
  }

  function decorateOrderCards() {
    const list = document.querySelector('#myOrdersList');
    if (!list) return;

    list.querySelectorAll('.mini-order').forEach(card => {
      if (card.querySelector('.maps-order-button')) return;

      const text = card.textContent || '';
      const match = text.match(/🏠\s*([\s\S]+)$/);
      const address = match ? match[1].trim() : '';
      const url = mapsUrl(address);
      if (!url) return;

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tool-action maps-order-button';
      button.style.marginTop = '10px';
      button.innerHTML = '<b>📍 BUKA GOOGLE MAPS</b><span>›</span>';
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram.WebApp.openLink(url);
        } else {
          window.open(url, '_blank', 'noopener,noreferrer');
        }
      });
      card.appendChild(button);
    });
  }

  function init() {
    decorateOrderCards();
    const list = document.querySelector('#myOrdersList');
    if (!list || list.dataset.mapsObserver === '1') return;
    list.dataset.mapsObserver = '1';
    new MutationObserver(decorateOrderCards).observe(list, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
