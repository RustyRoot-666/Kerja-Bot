(() => {
  'use strict';

  const KEY = 'kerja-miniapp-theme';
  const DARK = 'dark';
  const LIGHT = 'light';
  const TOGGLE_ID = 'kerjaThemeToggleIndependent';

  function getTheme() {
    return localStorage.getItem(KEY) === LIGHT ? LIGHT : DARK;
  }

  function applyTheme(theme) {
    const mode = theme === LIGHT ? LIGHT : DARK;

    document.documentElement.dataset.kerjaTheme = mode;

    if (document.body) {
      document.body.classList.toggle(
        'kerja-theme-light',
        mode === LIGHT
      );
    }

    const button = document.getElementById(TOGGLE_ID);

    if (button) {
      button.textContent = mode === LIGHT ? '🌙' : '☀️';
      button.title =
        mode === LIGHT
          ? 'Gunakan mode gelap'
          : 'Gunakan mode terang';

      button.setAttribute(
        'aria-label',
        mode === LIGHT
          ? 'Gunakan mode gelap'
          : 'Gunakan mode terang'
      );
    }

    localStorage.setItem(KEY, mode);
  }

  function createIndependentToggle() {
    let button = document.getElementById(TOGGLE_ID);

    if (!button) {
      button = document.createElement('button');

      button.id = TOGGLE_ID;
      button.type = 'button';

      /*
       * PENTING:
       * Tombol langsung ditempel ke <html>,
       * bukan ke card/header/container dashboard.
       */
      document.documentElement.appendChild(button);
    }

    button.style.cssText = `
      position: fixed !important;
      top: calc(env(safe-area-inset-top, 0px) + 72px) !important;
      right: 12px !important;
      width: 48px !important;
      height: 48px !important;
      min-width: 48px !important;
      min-height: 48px !important;
      z-index: 2147483647 !important;

      display: flex !important;
      align-items: center !important;
      justify-content: center !important;

      margin: 0 !important;
      padding: 0 !important;

      border: 1px solid rgba(90, 180, 255, .30) !important;
      border-radius: 50% !important;

      background: rgba(7, 24, 42, .94) !important;
      color: #ffffff !important;

      font-size: 22px !important;
      line-height: 1 !important;

      box-shadow: 0 4px 18px rgba(0, 0, 0, .35) !important;

      cursor: pointer !important;
      touch-action: manipulation !important;

      transform: none !important;
      filter: none !important;
    `;

    if (!button.dataset.bound) {
      button.dataset.bound = '1';

      button.addEventListener(
        'click',
        (event) => {
          event.preventDefault();
          event.stopPropagation();

          const next =
            getTheme() === DARK ? LIGHT : DARK;

          applyTheme(next);
        },
        true
      );
    }

    applyTheme(getTheme());
  }

  function hideOldThemeButtons() {
    const selectors = [
      '#themeToggle',
      '[data-theme-toggle]',
      '[aria-label*="theme" i]',
      '[aria-label*="tema" i]'
    ];

    document.querySelectorAll(selectors.join(',')).forEach((el) => {
      if (el.id !== TOGGLE_ID) {
        el.style.setProperty('display', 'none', 'important');
        el.style.setProperty('visibility', 'hidden', 'important');
        el.style.setProperty('pointer-events', 'none', 'important');
      }
    });
  }

  function injectLightModeCSS() {
    if (document.getElementById('kerja-miniapp-theme-css')) {
      return;
    }

    const style = document.createElement('style');

    style.id = 'kerja-miniapp-theme-css';

    style.textContent = `
      html[data-kerja-theme="light"] {
        color-scheme: light;
      }

      html[data-kerja-theme="dark"] {
        color-scheme: dark;
      }

      body.kerja-theme-light {
        background: #f4f7fb !important;
        color: #172033 !important;
      }

      body.kerja-theme-light .panel,
      body.kerja-theme-light .card,
      body.kerja-theme-light .kpi-card,
      body.kerja-theme-light .tool-card,
      body.kerja-theme-light .stat-card,
      body.kerja-theme-light .dashboard-card {
        background: #ffffff !important;
        color: #172033 !important;
        border-color: #d8e0eb !important;
      }

      body.kerja-theme-light input,
      body.kerja-theme-light select,
      body.kerja-theme-light textarea {
        background: #ffffff !important;
        color: #172033 !important;
        border-color: #cbd5e1 !important;
      }

      body.kerja-theme-light .bottom-nav {
        background: #ffffff !important;
        border-color: #d8e0eb !important;
      }

      body.kerja-theme-light .muted,
      body.kerja-theme-light .secondary,
      body.kerja-theme-light .subtle {
        color: #64748b !important;
      }
    `;

    document.head.appendChild(style);
  }

  function init() {
    injectLightModeCSS();
    hideOldThemeButtons();
    createIndependentToggle();
    applyTheme(getTheme());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
