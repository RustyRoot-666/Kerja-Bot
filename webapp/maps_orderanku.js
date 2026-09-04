// Google Maps integration for Mini App Orderanku.
// Normalizes Indonesian gang/street numbering before opening Google Maps.
// Example: KEDUNG TARUKAN BARU 4 55 -> KEDUNG TARUKAN BARU IV NO 55.

(function () {
  const ROMAN = [
    '', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
    'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX',
    'XXI', 'XXII', 'XXIII', 'XXIV', 'XXV', 'XXVI', 'XXVII', 'XXVIII', 'XXIX', 'XXX',
    'XXXI', 'XXXII', 'XXXIII', 'XXXIV', 'XXXV', 'XXXVI', 'XXXVII', 'XXXVIII', 'XXXIX', 'XL',
    'XLI', 'XLII', 'XLIII', 'XLIV', 'XLV', 'XLVI', 'XLVII', 'XLVIII', 'XLIX', 'L'
  ];

  function toRoman(value) {
    const number = Number(value);
    return Number.isInteger(number) && number > 0 && number < ROMAN.length
      ? ROMAN[number]
      : String(value);
  }

  function normalizeMapsAddress(address) {
    let value = String(address || '').trim().replace(/\s+/g, ' ');
    if (!value || value === '-') return '';

    // Common format used in the Orderanku data:
    // "NAMA GANG 4 55" => "NAMA GANG IV NO 55"
    // Also handles an existing NO before the house number.
    const match = value.match(/^(.*?\D)\s+(\d{1,2})\s+(?:NO\.?\s*)?(\d+[A-Z]?)$/i);
    if (match) {
      const gangNumber = Number(match[2]);
      if (gangNumber >= 1 && gangNumber <= 50) {
        return `${match[1].trim()} ${toRoman(gangNumber)} NO ${match[3].toUpperCase()}`;
      }
    }

    return value;
  }

  function mapsUrl(address) {
    const value = normalizeMapsAddress(address);
    if (!value) return '';
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
