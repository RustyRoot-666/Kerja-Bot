(() => {
  const tg = window.Telegram?.WebApp;
  const root = document.documentElement;
  const body = document.body;
  const $ = (s, p=document) => p.querySelector(s);
  const $$ = (s, p=document) => [...p.querySelectorAll(s)];

  function haptic(kind='light') {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_) {}
  }

  function toast(message) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden');
    el.classList.remove('toast-in');
    void el.offsetWidth;
    el.classList.add('toast-in');
    clearTimeout(window.__interactiveToastTimer);
    window.__interactiveToastTimer = setTimeout(() => {
      el.classList.remove('toast-in');
      setTimeout(() => el.classList.add('hidden'), 180);
    }, 1800);
  }

  function ensureWelcomeStatus() {
    const pill = $('.welcome-row .period-pill');
    if (!pill) return null;
    let wrap = $('.welcome-row .welcome-status');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'welcome-status';
      pill.parentNode.insertBefore(wrap, pill);
      wrap.appendChild(pill);
    }
    return wrap;
  }

  function setNetworkState() {
    const online = navigator.onLine;
    root.dataset.network = online ? 'online' : 'offline';
    const wrap = ensureWelcomeStatus();
    let badge = $('#networkBadge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'networkBadge';
      badge.setAttribute('role', 'status');
      badge.innerHTML = '<i></i><b></b>';
      (wrap || body).prepend(badge);
    } else if (wrap && badge.parentElement !== wrap) {
      wrap.prepend(badge);
    }
    const label = $('b', badge);
    if (label) label.textContent = online ? 'ONLINE' : 'OFFLINE';
    badge.classList.toggle('offline', !online);
    badge.title = online ? 'Koneksi aktif' : 'Koneksi terputus';
  }

  async function refreshCurrent() {
    haptic('medium');
    body.classList.add('is-refreshing');
    const active = $('.page-view:not(.hidden)')?.id || 'dashboardPage';
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
      setTimeout(() => body.classList.remove('is-refreshing'), 360);
    }
  }

  function linePath(points) {
    if (!points.length) return '';
    if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;
    let d = `M ${points[0][0]} ${points[0][1]}`;
    for (let i=1; i<points.length; i++) {
      const [x0,y0] = points[i-1];
      const [x1,y1] = points[i];
      const mx = (x0+x1)/2;
      d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
    }
    return d;
  }

  function upgradeTrendChart() {
    const chart = $('#trendChart');
    if (!chart || chart.dataset.fluidChart === '1') return;
    const cols = $$('.trend-col', chart);
    if (!cols.length) return;
    const rows = cols.map(col => ({
      value: Number(($('.trend-value', col)?.textContent || '0').replace(/[^0-9.-]/g,'')) || 0,
      label: $('.trend-label', col)?.textContent || ''
    }));
    if (!rows.length) return;

    const W=700, H=200, left=38, right=24, top=30, bottom=45;
    const plotBottom=H-bottom, plotHeight=plotBottom-top;
    const max=Math.max(1,...rows.map(r=>r.value));
    const step=rows.length>1?(W-left-right)/(rows.length-1):0;
    const points=rows.map((r,i)=>[left+i*step, plotBottom-(r.value/max)*plotHeight]);
    const path=linePath(points);
    const area=`${path} L ${points[points.length-1][0]} ${plotBottom} L ${points[0][0]} ${plotBottom} Z`;
    const dots=points.map(([x,y],i)=>`<g class="line-point" style="--i:${i}"><circle class="line-halo" cx="${x}" cy="${y}" r="9"/><circle class="line-dot" cx="${x}" cy="${y}" r="5"/><text class="line-value" x="${x}" y="${Math.max(16,y-15)}" text-anchor="middle">${rows[i].value}</text><line class="line-guide" x1="${x}" x2="${x}" y1="${y+9}" y2="${plotBottom}"/></g>`).join('');
    const labels=points.map(([x],i)=>`<text class="line-label" x="${x}" y="${H-14}" text-anchor="middle">${rows[i].label}</text>`).join('');

    chart.dataset.fluidChart='1';
    chart.innerHTML=`<svg class="trend-line-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Grafik garis trend order harian"><defs><linearGradient id="trendAreaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#42cfff" stop-opacity=".27"/><stop offset="100%" stop-color="#2387ff" stop-opacity="0"/></linearGradient><linearGradient id="trendStrokeGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#52dcff"/><stop offset="100%" stop-color="#2580ff"/></linearGradient><filter id="trendGlow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><line class="line-baseline" x1="${left}" x2="${W-right}" y1="${plotBottom}" y2="${plotBottom}"/><path class="trend-area-path" d="${area}"/><path class="trend-line-path" d="${path}" pathLength="1"/>${dots}${labels}</svg>`;
  }

  function observeTrend() {
    const chart = $('#trendChart');
    if (!chart) return;
    const observer = new MutationObserver(() => {
      if ($('.trend-col', chart)) {
        chart.dataset.fluidChart='0';
        requestAnimationFrame(upgradeTrendChart);
      }
    });
    observer.observe(chart,{childList:true,subtree:true});
    requestAnimationFrame(upgradeTrendChart);
  }

  function animateMetric(el) {
    if (!el || el.dataset.animating === '1') return;
    el.dataset.animating='1';
    el.classList.remove('metric-pop');
    void el.offsetWidth;
    el.classList.add('metric-pop');
    setTimeout(()=>{el.classList.remove('metric-pop');el.dataset.animating='0';},420);
  }

  function observeMetrics() {
    ['#totalClose','#activeTechnicians','#averageClose','#ringValue','#myOrderCount'].forEach(sel=>{
      const el=$(sel); if(!el)return;
      new MutationObserver(()=>animateMetric(el)).observe(el,{childList:true,characterData:true,subtree:true});
    });
  }

  function enhanceEntrance() {
    $$('.kpi-card,.dashboard-grid>.panel').forEach((el,i)=>el.style.setProperty('--enter-delay',`${Math.min(i*42,260)}ms`));
  }

  document.addEventListener('pointerdown', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row,.kpi-card');
    if (target) target.classList.add('pressing');
  }, {passive:true});

  document.addEventListener('pointerup', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row,.kpi-card');
    if (target) {
      target.classList.remove('pressing');
      haptic('light');
    }
  }, {passive:true});

  document.addEventListener('pointercancel', () => $$('.pressing').forEach(el=>el.classList.remove('pressing')), {passive:true});

  window.addEventListener('online', () => { setNetworkState(); toast('Koneksi kembali online'); });
  window.addEventListener('offline', () => { setNetworkState(); toast('Koneksi terputus'); });

  let startY=0, pulling=false, indicator;
  function ensureIndicator() {
    if (indicator) return indicator;
    indicator=document.createElement('div');
    indicator.id='pullRefresh';
    indicator.innerHTML='<span>↻</span><b>Tarik untuk refresh</b>';
    body.appendChild(indicator);
    return indicator;
  }
  document.addEventListener('touchstart',e=>{if(window.scrollY>2||e.touches.length!==1)return;startY=e.touches[0].clientY;pulling=true;},{passive:true});
  document.addEventListener('touchmove',e=>{if(!pulling)return;const delta=Math.max(0,Math.min(95,e.touches[0].clientY-startY));if(delta<8)return;const el=ensureIndicator();el.style.transform=`translate(-50%, ${Math.min(58,delta*.6)}px)`;el.classList.toggle('ready',delta>70);$('b',el).textContent=delta>70?'Lepas untuk refresh':'Tarik untuk refresh';},{passive:true});
  document.addEventListener('touchend',async e=>{if(!pulling)return;pulling=false;const delta=e.changedTouches?.[0]?e.changedTouches[0].clientY-startY:0;if(indicator)indicator.style.transform='translate(-50%,-60px)';if(delta>70)await refreshCurrent();},{passive:true});

  const style=document.createElement('style');
  style.textContent=`
    html{scroll-behavior:smooth}body{overflow-x:hidden;background-attachment:fixed}
    .welcome-status{display:flex;flex-direction:column;align-items:stretch;gap:7px;min-width:128px}
    #networkBadge{position:static;align-self:flex-end;display:inline-flex;align-items:center;gap:7px;min-height:24px;padding:5px 9px;border:1px solid rgba(63,221,153,.30);border-radius:999px;background:linear-gradient(180deg,rgba(8,38,42,.82),rgba(4,24,31,.72));backdrop-filter:blur(12px);color:#5ee6a5;font:800 8px/1 system-ui;letter-spacing:.11em;pointer-events:none;box-shadow:0 7px 20px rgba(0,0,0,.12);transition:color .35s ease,border-color .35s ease,background .35s ease,transform .35s cubic-bezier(.2,.8,.2,1)}
    #networkBadge i{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px rgba(94,230,165,.08),0 0 12px currentColor;animation:networkPulse 2.2s ease-in-out infinite}#networkBadge.offline{color:#ff7480;border-color:rgba(255,91,108,.35);background:rgba(44,9,17,.76)}
    @keyframes networkPulse{0%,100%{transform:scale(.88);opacity:.7}50%{transform:scale(1.08);opacity:1}}

    .round-btn,.segment,.period,.nav-item,.tool-action,.leader-row,.area-row,.mini-order,.kpi-card,.panel,.pay-stat,.detail-metrics>div{transition:transform .28s cubic-bezier(.2,.8,.2,1),border-color .28s ease,background .28s ease,box-shadow .32s ease,filter .24s ease,opacity .24s ease}
    .round-btn:active,.segment:active,.period:active,.nav-item:active{transform:scale(.94)}
    .pressing{transform:scale(.975)!important;filter:brightness(1.10);transition-duration:.09s!important}
    .segment.active,.period.active{transform:translateY(-1px);box-shadow:0 8px 24px rgba(36,135,255,.28)}
    .segmented{overflow:hidden;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    .kpi-card,.panel{backdrop-filter:blur(12px)}
    .kpi-card{animation:cardEnter .5s cubic-bezier(.16,.82,.25,1) both;animation-delay:var(--enter-delay,0ms)}
    .dashboard-grid>.panel{animation:panelEnter .55s cubic-bezier(.16,.82,.25,1) both;animation-delay:var(--enter-delay,0ms)}
    @keyframes cardEnter{from{opacity:0;transform:translateY(13px) scale(.985)}to{opacity:1;transform:none}}
    @keyframes panelEnter{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
    .kpi-icon{transition:transform .35s cubic-bezier(.2,.8,.2,1),box-shadow .35s ease}.kpi-card:active .kpi-icon{transform:scale(1.08) rotate(-3deg)}
    .metric-pop{animation:metricPop .4s cubic-bezier(.2,.9,.2,1)}@keyframes metricPop{0%{transform:translateY(5px);opacity:.35}55%{transform:translateY(-2px) scale(1.04)}100%{transform:none;opacity:1}}

    .trend-chart{height:218px!important;display:block!important;padding:6px 0 0!important;position:relative;overflow:visible}
    .trend-line-svg{width:100%;height:100%;overflow:visible;display:block}
    .line-baseline{stroke:rgba(116,153,190,.22);stroke-width:1}.trend-area-path{fill:url(#trendAreaGradient);opacity:0;animation:areaFade .7s .2s ease forwards}.trend-line-path{fill:none;stroke:url(#trendStrokeGradient);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;filter:url(#trendGlow);stroke-dasharray:1;stroke-dashoffset:1;animation:drawTrend .9s cubic-bezier(.2,.75,.2,1) forwards}
    .line-guide{stroke:rgba(76,161,255,.16);stroke-width:1;stroke-dasharray:4 5}.line-dot{fill:#eaf7ff;stroke:#2d91ff;stroke-width:4;filter:url(#trendGlow)}.line-halo{fill:rgba(66,207,255,.11);stroke:none}.line-value{fill:#eaf6ff;font-size:15px;font-weight:800}.line-label{fill:#7e96af;font-size:13px;font-weight:700}.line-point{opacity:0;animation:pointIn .34s cubic-bezier(.2,.9,.2,1) forwards;animation-delay:calc(.42s + var(--i)*.07s)}
    @keyframes drawTrend{to{stroke-dashoffset:0}}@keyframes areaFade{to{opacity:1}}@keyframes pointIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

    .bottom-nav{box-shadow:0 20px 55px rgba(0,0,0,.32),inset 0 1px 0 rgba(255,255,255,.045);transition:transform .3s ease,background .3s ease}.nav-item.active{transform:translateY(-1px)}.nav-item.active span{filter:drop-shadow(0 0 9px rgba(75,167,255,.42))}.nav-plus span{animation:plusBreathe 3.4s ease-in-out infinite}@keyframes plusBreathe{0%,100%{box-shadow:0 0 25px rgba(31,123,255,.36)}50%{box-shadow:0 0 34px rgba(31,123,255,.56)}}
    .leader-row:hover,.area-row:hover,.tool-action:hover{background:rgba(38,91,139,.10)}
    .search-wrap:focus-within{border-color:#3f82bd;box-shadow:0 0 0 3px rgba(49,142,224,.08)}

    .detail-backdrop,.drawer-backdrop,.more-backdrop{animation:fadeBackdrop .24s ease-out}.detail-sheet{animation:sheetUp .38s cubic-bezier(.16,.82,.25,1)}.drawer-sheet{animation:drawerIn .34s cubic-bezier(.16,.82,.25,1)}.more-box{transform-origin:top right;animation:menuIn .2s cubic-bezier(.2,.85,.2,1)}
    @keyframes fadeBackdrop{from{opacity:0}to{opacity:1}}@keyframes sheetUp{from{transform:translateY(28px);opacity:.55}to{transform:none;opacity:1}}@keyframes drawerIn{from{transform:translateX(-35px);opacity:.4}to{transform:none;opacity:1}}@keyframes menuIn{from{transform:translateY(-5px) scale(.96);opacity:0}to{transform:none;opacity:1}}
    .toast{transition:opacity .18s ease,transform .18s cubic-bezier(.2,.8,.2,1)}.toast-in{animation:toastIn .28s cubic-bezier(.2,.9,.2,1)}@keyframes toastIn{from{opacity:0;transform:translate(-50%,10px) scale(.96)}to{opacity:1;transform:translate(-50%,0) scale(1)}}

    body.is-refreshing .app-header .brand-center strong::after{content:' ↻';display:inline-block;animation:uiSpin .65s linear infinite;color:#55d9ff}
    body.is-refreshing .dashboardPage,body.is-refreshing #dashboardPage{opacity:.82}
    @keyframes uiSpin{to{transform:rotate(360deg)}}
    #pullRefresh{position:fixed;z-index:260;left:50%;top:-52px;transform:translate(-50%,-60px);display:flex;align-items:center;gap:8px;border:1px solid #284762;background:rgba(7,24,40,.95);box-shadow:0 10px 30px rgba(0,0,0,.35);border-radius:999px;padding:8px 12px;color:#90a8be;font:700 10px system-ui;transition:transform .18s cubic-bezier(.2,.8,.2,1)}#pullRefresh span{font-size:15px;color:#55d9ff}#pullRefresh.ready{color:#e9f7ff;border-color:#45b9df}#pullRefresh.ready span{animation:uiSpin .65s linear infinite}
    .page-view{animation:pageIn .34s cubic-bezier(.16,.82,.25,1)}@keyframes pageIn{from{opacity:.45;transform:translateY(12px) scale(.995)}to{opacity:1;transform:none}}

    @media(hover:hover){.kpi-card:hover,.panel:hover{transform:translateY(-2px);border-color:#335579;box-shadow:0 18px 45px rgba(0,0,0,.23)}.round-btn:hover{border-color:#3d668d;background:#10253b}}
    @media(max-width:430px){.welcome-status{min-width:112px;gap:6px}#networkBadge{padding:4px 8px}.trend-chart{height:200px!important}.line-value{font-size:14px}.line-label{font-size:12px}}
    @media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.page-view,.pressing,#pullRefresh,.kpi-card,.dashboard-grid>.panel,.trend-line-path,.trend-area-path,.line-point,.nav-plus span,#networkBadge i,.detail-sheet,.drawer-sheet,.more-box{animation:none!important;transition:none!important}}
  `;
  document.head.appendChild(style);

  setNetworkState();
  enhanceEntrance();
  observeTrend();
  observeMetrics();
  tg?.setHeaderColor?.('#06111f');
  tg?.setBackgroundColor?.('#06111f');
})();
