/* Orderanku v2: Smart Order Card + lifecycle + broad operational area grouping. */
(function () {
  const ROMAN = ['', 'I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX','XXI','XXII','XXIII','XXIV','XXV','XXVI','XXVII','XXVIII','XXIX','XXX','XXXI','XXXII','XXXIII','XXXIV','XXXV','XXXVI','XXXVII','XXXVIII','XXXIX','XL','XLI','XLII','XLIII','XLIV','XLV','XLVI','XLVII','XLVIII','XLIX','L'];
  const clean = v => String(v || '').trim().replace(/\s+/g, ' ');
  const upper = v => clean(v).toUpperCase().replace(/[^A-Z0-9\s-]+/g,' ').replace(/\s+/g,' ').trim();
  const todayKey = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Jakarta'}).format(new Date());
  const esc2 = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt2 = v => (typeof fmt === 'function' ? fmt(v) : Number(v || 0).toLocaleString('id-ID'));

  function normalizeAddress(address) {
    let value = clean(address);
    if (!value || value === '-') return '';
    const match = value.match(/^(.*?\D)\s+(\d{1,2})\s+(?:NO\.?\s*)?(\d+[A-Z]?)$/i);
    if (match) {
      const n = Number(match[2]);
      if (n >= 1 && n <= 50) return `${match[1].trim()} ${ROMAN[n]} NO ${match[3].toUpperCase()}`;
    }
    return value;
  }

  // Operational buckets only. Never split Bumi Marina / Semolowaru / street names into separate areas.
  function operationalArea(order) {
    const raw = upper(`${order?.address || ''} ${order?.area_label || ''} ${order?.area || ''}`);
    if (/\bJAGIR\b|\bJGR\b|WONOKROMO/.test(raw)) return 'JAGIR';
    if (/\bNGINDEN\b|NGINDEN JANGKUNGAN|NGINDEN SEMOLO|NGINDEN INTAN|NGINDEN BARU/.test(raw)) return 'NGINDEN';
    if (/\bSEMOLO\b|SEMOLOWARU|KEPUTIH|BUMI MARINA|MEDOKAN SEMAMPIR|KLAMPIS NGASEM|MENUR PUMPUNGAN|GEBANG PUTIH/.test(raw)) return 'SEMOLO';
    const existing = upper(order?.area || order?.area_label || '');
    if (existing === 'NGINDEN' || existing === 'SEMOLO' || existing === 'JAGIR') return existing;
    return 'LAINNYA';
  }

  function mapsUrl(address) {
    const q = normalizeAddress(address);
    return q ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}` : '';
  }
  function callUrl(phone) {
    const p = clean(phone).replace(/[^0-9+]/g, '');
    return p ? `tel:${p}` : '';
  }
  function lifecycle(order, completed) {
    if (completed || String(order.source || '').includes('miniapp')) return {label:'COMPLETED', icon:'✅', pct:100, cls:'done'};
    const status = String(order.status || '').toUpperCase();
    if (status.includes('PROGRESS') || status.includes('UPDATE') || status.includes('PENDING')) return {label:'ON PROGRESS', icon:'🟡', pct:55, cls:'progress'};
    if (order.config_description || order.report_description) return {label:'REPORT', icon:'📝', pct:80, cls:'progress'};
    return {label:'OPEN', icon:'🟢', pct:25, cls:'open'};
  }
  function stageHtml(stage) {
    return `<div class="order-life"><div class="order-life-head"><span>${stage.icon} ${stage.label}</span><strong>${stage.pct}%</strong></div><div class="order-life-track"><i class="${stage.cls}" style="width:${stage.pct}%"></i></div><div class="order-life-steps"><span class="${stage.pct>=25?'active':''}">OPEN</span><span class="${stage.pct>=55?'active':''}">PROGRESS</span><span class="${stage.pct>=80?'active':''}">REPORT</span><span class="${stage.pct>=100?'active':''}">DONE</span></div></div>`;
  }
  function card(order, completed=false, index=0) {
    const stage = lifecycle(order, completed);
    const address = normalizeAddress(order.address || '');
    const map = mapsUrl(address);
    const call = callUrl(order.customer_phone);
    const day = String(order.raw_day || order.date || '').slice(0,10);
    const source = order.source === 'miniapp' ? 'MINI APP' : order.source === 'miniapp+report' ? 'MINI APP + REPORT' : completed ? 'REPORT' : 'ORDER SHEET';
    return `<article class="smart-order-card ${stage.cls}" data-order-service="${esc2(order.service_number)}">
      <div class="smart-order-top"><span class="smart-order-index">${index + 1}</span><div class="smart-order-title"><strong>🌐 ${esc2(order.service_number || '-')}</strong><small>${esc2(order.ticket_id || 'MANUAL')} • ${esc2(source)}</small></div><b class="status-pill ${stage.cls}">${stage.icon} ${stage.label}</b></div>
      <div class="smart-order-customer"><strong>${esc2(order.customer_name || '-')}</strong><span>📞 ${esc2(order.customer_phone || '-')}</span></div>
      <div class="smart-order-grid"><span>⚡ ${esc2(order.package || '-')}</span><span>📡 RX ${esc2(order.onu_rx || '-')}</span><span>📝 RCA ${esc2(order.rca || '-')}</span><span>📍 ${esc2(order.sto || order.area_label || '-')}</span></div>
      <div class="smart-order-address">🏠 ${esc2(address || order.address || '-')}</div>
      ${stageHtml(stage)}
      <div class="smart-order-actions">${map ? `<button type="button" class="smart-action" data-map-url="${esc2(map)}">📍 Maps</button>` : ''}${call ? `<a class="smart-action" href="${esc2(call)}">📞 Call</a>` : ''}<button type="button" class="smart-action detail-toggle">📋 Detail</button></div>
      <div class="smart-order-detail hidden"><div>🎫 Tiket: <b>${esc2(order.ticket_id || 'MANUAL')}</b></div><div>📡 ONU RX: <b>${esc2(order.onu_rx || '-')}</b></div><div>🔧 ONT: <b>${esc2(order.ont_type || '-')}</b></div><div>🔢 SN Lama: <b>${esc2(order.old_sn || '-')}</b></div><div>🔢 SN Baru: <b>${esc2(order.new_sn || '-')}</b></div><div>🆔 VALINS: <b>${esc2(order.valins_id || '-')}</b></div><div>🕐 Tanggal: <b>${esc2(day || '-')}</b></div></div>
    </article>`;
  }

  function injectStyle() {
    if (document.querySelector('#orderUiUpgradeStyle')) return;
    const s = document.createElement('style'); s.id='orderUiUpgradeStyle';
    s.textContent = `.smart-order-card{border:1px solid #254463;background:linear-gradient(180deg,#0d1d31,#081522);border-radius:17px;padding:13px;margin-bottom:9px;color:#edf6ff;box-shadow:0 8px 24px rgba(0,0,0,.16)}.smart-order-top{display:flex;align-items:flex-start;gap:9px}.smart-order-index{width:25px;height:25px;border-radius:8px;background:#122a43;display:grid;place-items:center;font-size:10px;color:#9bb2c9}.smart-order-title{min-width:0;flex:1}.smart-order-title strong{display:block;font-size:13px}.smart-order-title small{display:block;color:#7189a1;font-size:9px;margin-top:3px}.status-pill{font-size:8px;border:1px solid #31516f;border-radius:999px;padding:5px 7px;white-space:nowrap}.status-pill.done{border-color:#2b8066}.status-pill.progress{border-color:#8a6c28}.status-pill.open{border-color:#286b55}.smart-order-customer{display:flex;justify-content:space-between;gap:8px;margin:12px 0 8px}.smart-order-customer strong{font-size:12px}.smart-order-customer span{font-size:9px;color:#849ab0}.smart-order-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;color:#9eb2c5;font-size:9px}.smart-order-address{margin-top:8px;padding:8px;border-radius:10px;background:#071321;color:#c8d7e5;font-size:9px;line-height:1.45}.order-life{margin-top:10px}.order-life-head{display:flex;justify-content:space-between;color:#9fb3c7;font-size:9px}.order-life-head strong{color:#e7f4ff}.order-life-track{height:5px;background:#15283c;border-radius:99px;overflow:hidden;margin:6px 0}.order-life-track i{display:block;height:100%;border-radius:99px;background:#55d9ff}.order-life-track i.done{background:#2bd08f}.order-life-track i.progress{background:#ffbf4d}.order-life-track i.open{background:#55d9ff}.order-life-steps{display:flex;justify-content:space-between;color:#536b83;font-size:7px}.order-life-steps .active{color:#d5e8f7}.smart-order-actions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px}.smart-action{display:flex;align-items:center;justify-content:center;min-height:32px;border:1px solid #294967;border-radius:10px;background:#0b1c30;color:#dceeff;text-decoration:none;font-size:9px}.smart-action:hover{background:#102a43}.smart-order-detail{margin-top:9px;padding:9px;border-radius:10px;background:#06111f;border:1px solid #1e3852;font-size:9px;line-height:1.8;color:#9eb3c8}.smart-order-detail:not(.hidden){display:grid;grid-template-columns:1fr 1fr;gap:2px 9px}.order-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}.order-tab{border:1px solid #294967;background:#091a2b;color:#91a8be;border-radius:10px;padding:9px 5px;font-size:9px}.order-tab.active{color:#eaf7ff;border-color:#4aa5d1;background:#102a42}.order-summary-v2{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:8px 0}.order-summary-v2 div{border:1px solid #223f5c;background:#0a1929;border-radius:12px;padding:9px;text-align:center}.order-summary-v2 span{display:block;color:#7089a1;font-size:7px}.order-summary-v2 strong{display:block;font-size:18px;margin-top:3px}.order-area-grid{display:grid;gap:8px;margin-top:8px}.order-area-btn{width:100%;border:1px solid #294967;background:linear-gradient(180deg,#0d2136,#091727);color:#e8f5ff;border-radius:14px;padding:13px;text-align:left;display:flex;align-items:center;justify-content:space-between;gap:10px}.order-area-btn:active{transform:scale(.99)}.order-area-name{font-size:12px;font-weight:800}.order-area-meta{display:block;color:#7890a8;font-size:9px;margin-top:5px}.order-area-arrow{font-size:18px;color:#58d5ff}.order-area-back{margin:8px 0;border:1px solid #294967;background:#0a1c2e;color:#dceeff;border-radius:10px;padding:9px 12px;font-size:9px}`;
    document.head.appendChild(s);
  }

  async function loadReportForOrders() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u?.id) return null;
    try { const r = await fetch(`/api/my-report?telegram_id=${encodeURIComponent(String(u.id))}`, {cache:'no-store'}); if (!r.ok) return null; const d = await r.json(); return d?.ok ? d : null; } catch (_) { return null; }
  }
  function flattenOpen(data) {
    const rows=[];
    (data?.areas || []).forEach(area => (area.orders || []).forEach(order => rows.push({...order,status:'OPEN',_bucket:'open',area_label:order.area_label || area.area})));
    return rows;
  }
  function merge(openRows, report) {
    const map = new Map();
    openRows.forEach(o => map.set(String(o.service_number), o));
    (report?.orders || []).forEach(o => { const key=String(o.service_number || ''); if (!key) return; const existing=map.get(key); const day=String(o.raw_day || o.date || '').slice(0,10); const isDone=String(o.source || '').includes('miniapp') || Boolean(day); if (!existing || isDone) map.set(key,{...(existing||{}),...o,status:isDone?'COMPLETED':(o.status||'CLOSE'),_bucket:isDone?'completed':'close'}); });
    return [...map.values()];
  }
  function setSummary(rows, report) {
    const today=todayKey(); const done=rows.filter(o=>o._bucket==='completed' && String(o.raw_day||o.date||'').slice(0,10)===today).length; const open=rows.filter(o=>o._bucket==='open').length; const all=rows.filter(o=>o._bucket==='completed').length;
    const el=document.querySelector('#myOrderSummary'); if(el) el.innerHTML=`<div><span>OPEN</span><strong>${fmt2(open)}</strong></div><div><span>CLOSE HARI INI</span><strong>${fmt2(done)}</strong></div><div><span>TOTAL SELESAI</span><strong>${fmt2(report?.all || all)}</strong></div>`;
  }

  function filteredRows(rows, mode) {
    const today=todayKey();
    if(mode==='today') return rows.filter(o=>o._bucket==='open' || (o._bucket==='completed' && String(o.raw_day||o.date||'').slice(0,10)===today));
    if(mode==='open') return rows.filter(o=>o._bucket==='open');
    return rows.filter(o=>o._bucket==='completed');
  }
  function groupRows(rows) {
    const map=new Map(); const priority=['NGINDEN','SEMOLO','JAGIR','LAINNYA'];
    rows.forEach(o=>{ const area=operationalArea(o); if(!map.has(area)) map.set(area,{area,orders:[]}); map.get(area).orders.push(o); });
    return [...map.values()].sort((a,b)=>priority.indexOf(a.area)-priority.indexOf(b.area));
  }
  function bindCards(list) {
    list.querySelectorAll('.detail-toggle').forEach(b=>b.addEventListener('click',()=>b.parentElement.parentElement.querySelector('.smart-order-detail')?.classList.toggle('hidden')));
    list.querySelectorAll('[data-map-url]').forEach(b=>b.addEventListener('click',()=>{const url=b.dataset.mapUrl;if(window.Telegram?.WebApp?.openLink)window.Telegram.WebApp.openLink(url);else window.open(url,'_blank','noopener,noreferrer');}));
  }
  function renderCards(rows, mode, title) {
    const list=document.querySelector('#myOrdersList'), count=document.querySelector('#myOrderCount'); if(!list||!count)return;
    count.textContent=`${rows.length} data`;
    const back=document.createElement('button'); back.type='button'; back.className='order-area-back'; back.innerHTML='‹ Kembali ke daftar area'; back.addEventListener('click',()=>renderAreas(rows,mode)); list.replaceChildren(back);
    const heading=document.createElement('div'); heading.style.cssText='padding:4px 2px 9px;color:#a8bfd4;font-size:10px;font-weight:700'; heading.textContent=`📍 ${title} • ${rows.length} order`; list.appendChild(heading);
    rows.forEach((o,i)=>{ const wrap=document.createElement('div'); wrap.innerHTML=card(o,o._bucket==='completed',i); list.appendChild(wrap.firstElementChild); });
    list.dataset.areaDetail='1'; bindCards(list);
  }
  function renderAreas(rows, mode) {
    const list=document.querySelector('#myOrdersList'), count=document.querySelector('#myOrderCount'); if(!list||!count)return;
    const groups=groupRows(rows); count.textContent=`${rows.length} data`; list.replaceChildren();
    if(!groups.length){list.innerHTML='<div class="empty"><p>📭 Tidak ada pekerjaan pada filter ini.</p></div>';return;}
    const grid=document.createElement('div'); grid.className='order-area-grid';
    groups.forEach(g=>{ const b=document.createElement('button'); b.type='button'; b.className='order-area-btn'; b.innerHTML=`<div><span class="order-area-name">📍 ${esc2(g.area)}</span><small class="order-area-meta">🟢 ${g.orders.length} order</small></div><span class="order-area-arrow">›</span>`; b.addEventListener('click',()=>renderCards(g.orders,mode,g.area)); grid.appendChild(b); });
    list.appendChild(grid); list.dataset.areaDetail='0';
  }
  function render(rows, mode='today') { renderAreas(filteredRows(rows,mode),mode); }
  function tabs(rows, report) {
    const page=document.querySelector('#ordersPage'), panel=page?.querySelector('.panel'); if(!panel)return;
    const old=panel.querySelector('.order-tabs'); if(old)old.remove();
    const summary=document.querySelector('#myOrderSummary'); if(summary && !summary.classList.contains('order-summary-v2')) summary.classList.add('order-summary-v2');
    const tabs=document.createElement('div'); tabs.className='order-tabs';
    [['today','📅 Hari Ini'],['open','🟢 Open'],['completed','✅ Selesai']].forEach(([mode,label],i)=>{const b=document.createElement('button');b.className=`order-tab ${i===0?'active':''}`;b.textContent=label;b.addEventListener('click',()=>{tabs.querySelectorAll('.order-tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');render(rows,mode);});tabs.appendChild(b);});
    panel.querySelector('.panel-head')?.after(tabs); setSummary(rows,report); render(rows,'today');
  }

  const originalLoad = window.loadMyOpenOrders;
  window.loadMyOpenOrders = async function upgradedLoadMyOpenOrders(force=false) {
    injectStyle();
    const id=document.querySelector('#ordersIdentity'), list=document.querySelector('#myOrdersList');
    if(!id||!list)return originalLoad ? originalLoad(force) : null;
    id.textContent='🔄 Menyusun area operasional...'; list.innerHTML='<div class="empty"><p>Memuat Orderanku...</p></div>';
    try {
      const open=await window.fetchMyOpenOrders(force); const report=await loadReportForOrders(); const rows=merge(flattenOpen(open),report);
      window.__KerjaBotMyOpenRows=rows;
      window.__KerjaBotMyOpenPayload=open;
      id.textContent=`${open.technician?.name || report?.technician?.name || (typeof telegramName==='function'?telegramName():'Teknisi') || 'Teknisi'} • NIK ${open.technician?.nik || report?.technician?.nik || '-'} • Smart Order`;
      tabs(rows,report);
    } catch(e) { id.textContent='❌ Orderanku gagal dimuat'; list.innerHTML=`<div class="empty"><p>${esc2(e.message || 'Gagal membaca data.')}</p></div>`; }
  };
  window.KerjaBotOrderArea={operationalArea,groupRows,renderAreas,renderCards};
  injectStyle();
})();
