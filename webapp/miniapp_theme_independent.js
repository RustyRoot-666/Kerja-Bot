(() => {
  'use strict';

  const KEY = 'kerja-miniapp-theme';
  const DARK = 'dark';
  const LIGHT = 'light';

  function getTheme() {
    const saved = localStorage.getItem(KEY);
    return saved === LIGHT ? LIGHT : DARK;
  }

  function findToggle() {
    return document.querySelector(
      '#themeToggle, [data-theme-toggle], [aria-label*="theme" i], [aria-label*="tema" i]'
    );
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

    const button = findToggle();

    if (button) {
      button.dataset.kerjaThemeToggle = mode;
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

  function ensureToggle() {
    let button = findToggle();

    if (!button) {
      button = document.createElement('button');

      button.type = 'button';
      button.id = 'themeToggle';
      button.dataset.themeToggle = '1';

      button.style.cssText = [
        'cursor:pointer',
        'border:0',
        'background:transparent',
        'font-size:20px',
        'line-height:1',
        'padding:6px'
      ].join(';');

      const header =
        document.querySelector('header') ||
        document.querySelector('.topbar') ||
        document.querySelector('.header') ||
        document.body;

      header.appendChild(button);
    }

    if (!button.dataset.kerjaThemeBound) {
      button.dataset.kerjaThemeBound = '1';

      button.addEventListener(
        'click',
        (event) => {
          event.preventDefault();
          event.stopPropagation();

          const current = getTheme();
          applyTheme(current === DARK ? LIGHT : DARK);
        },
        true
      );
    }

    applyTheme(getTheme());
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
    ensureToggle();
    applyTheme(getTheme());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
