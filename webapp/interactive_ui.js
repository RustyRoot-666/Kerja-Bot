(() => {
  const tg = window.Telegram?.WebApp;
  const root = document.documentElement;
  const body = document.body;

  function haptic(kind='light') {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_) {}
  }

  function toast(message) {
    const el = document.querySelector('#toast');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden');
    clearTimeout(window.__interactiveToastTimer);
    window.__interactiveToastTimer = setTimeout(() => el.classList.add('hidden'), 1800);
  }

  function setNetworkState() {
    const online = navigator.onLine;
    root.dataset.network = online ? 'online' : 'offline';
    let badge = document.querySelector('#networkBadge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'networkBadge';
      badge.setAttribute('role', 'status');
      badge.innerHTML = '<span></span><b></b>';
      body.appendChild(badge);
    }
    badge.querySelector('span').textContent = online ? '●' : '●';
    badge.querySelector('b').textContent = online ? 'ONLINE' : 'OFFLINE';
    badge.classList.toggle('offline', !online);
  }

  async function refreshCurrent() {
    haptic('medium');
    body.classList.add('is-refreshing');
    const active = document.querySelector('.page-view:not(.hidden)')?.id || 'dashboardPage';
    try {
      if (active === 'dashboardPage' && typeof window.loadDashboard === 'function') await window.loadDashboard();
      else if (active === 'ordersPage' && typeof window.loadMyOpenOrders === 'function') await window.loadMyOpenOrders(true);
      else if (active === 'reportsPage' && typeof window.loadMyReport === 'function') await window.loadMyReport();
      else window.location.reload();
      toast('Data diperbarui');
    } catch (err) {
      console.error(err);
      toast('Refresh gagal');
    } finally {
      setTimeout(() => body.classList.remove('is-refreshing'), 250);
    }
  }

  document.addEventListener('pointerdown', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row');
    if (target) target.classList.add('pressing');
  }, {passive:true});

  document.addEventListener('pointerup', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row');
    if (target) {
      target.classList.remove('pressing');
      haptic('light');
    }
  }, {passive:true});

  document.addEventListener('pointercancel', () => {
    document.querySelectorAll('.pressing').forEach(el => el.classList.remove('pressing'));
  }, {passive:true});

  window.addEventListener('online', () => { setNetworkState(); toast('Koneksi kembali online'); });
  window.addEventListener('offline', () => { setNetworkState(); toast('Koneksi terputus'); });

  let startY = 0;
  let pulling = false;
  let indicator;
  function ensureIndicator() {
    if (indicator) return indicator;
    indicator = document.createElement('div');
    indicator.id = 'pullRefresh';
    indicator.innerHTML = '<span>↻</span><b>Tarik untuk refresh</b>';
    body.appendChild(indicator);
    return indicator;
  }
  document.addEventListener('touchstart', e => {
    if (window.scrollY > 2 || e.touches.length !== 1) return;
    startY = e.touches[0].clientY;
    pulling = true;
  }, {passive:true});
  document.addEventListener('touchmove', e => {
    if (!pulling) return;
    const delta = Math.max(0, Math.min(95, e.touches[0].clientY - startY));
    if (delta < 8) return;
    const el = ensureIndicator();
    el.style.transform = `translate(-50%, ${Math.min(58, delta * .6)}px)`;
    el.classList.toggle('ready', delta > 70);
    el.querySelector('b').textContent = delta > 70 ? 'Lepas untuk refresh' : 'Tarik untuk refresh';
  }, {passive:true});
  document.addEventListener('touchend', async e => {
    if (!pulling) return;
    pulling = false;
    const delta = e.changedTouches?.[0] ? e.changedTouches[0].clientY - startY : 0;
    if (indicator) indicator.style.transform = 'translate(-50%, -60px)';
    if (delta > 70) await refreshCurrent();
  }, {passive:true});

  const style = document.createElement('style');
  style.textContent = `
    #networkBadge{position:fixed;right:12px;top:max(8px,env(safe-area-inset-top));z-index:250;display:flex;align-items:center;gap:5px;padding:5px 8px;border:1px solid rgba(63,221,153,.35);border-radius:999px;background:rgba(4,23,32,.82);backdrop-filter:blur(10px);color:#5ee6a5;font:700 8px/1 system-ui;letter-spacing:.08em;opacity:.8;pointer-events:none;transition:.25s}#networkBadge.offline{color:#ff6f7c;border-color:rgba(255,91,108,.4);background:rgba(44,9,17,.86)}
    .pressing{transform:scale(.975)!important;filter:brightness(1.08);transition:transform .08s ease,filter .08s ease!important}
    body.is-refreshing .app-header .brand-center strong::after{content:' ↻';display:inline-block;animation:uiSpin .65s linear infinite;color:#55d9ff}
    @keyframes uiSpin{to{transform:rotate(360deg)}}
    #pullRefresh{position:fixed;z-index:260;left:50%;top:-52px;transform:translate(-50%,-60px);display:flex;align-items:center;gap:8px;border:1px solid #284762;background:rgba(7,24,40,.95);box-shadow:0 10px 30px rgba(0,0,0,.35);border-radius:999px;padding:8px 12px;color:#90a8be;font:700 10px system-ui;transition:transform .15s ease}#pullRefresh span{font-size:15px;color:#55d9ff}#pullRefresh.ready{color:#e9f7ff;border-color:#45b9df}#pullRefresh.ready span{animation:uiSpin .65s linear infinite}
    .page-view{animation:pageIn .18s ease-out}@keyframes pageIn{from{opacity:.65;transform:translateY(4px)}to{opacity:1;transform:none}}
    @media (prefers-reduced-motion:reduce){.page-view,.pressing,#pullRefresh{animation:none!important;transition:none!important}}
  `;
  document.head.appendChild(style);

  setNetworkState();
  tg?.setHeaderColor?.('#06111f');
  tg?.setBackgroundColor?.('#06111f');
})();
