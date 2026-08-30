(() => {
  const $ = (s, p=document) => p.querySelector(s);
  const $$ = (s, p=document) => [...p.querySelectorAll(s)];
  const escHtml = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isManja = order => /(^|\b)MANJA(\b|$)/i.test(String(order?.rca || order?.status_rca || order?.kendala || ''));
  const allManja = data => {
    const rows=[];
    (data?.areas || []).forEach(area => (area.orders || []).forEach(order => {
      if (isManja(order)) rows.push({...order, __area: area.area || order.area || '-'});
    }));
    return rows;
  };

  function ensureStyles(){
    if ($('#manjaStyles')) return;
    const style=document.createElement('style');
    style.id='manjaStyles';
    style.textContent=`
      .manja-banner{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:10px 0 12px;padding:13px 14px;border:1px solid rgba(255,190,47,.32);border-radius:17px;background:linear-gradient(135deg,rgba(87,56,6,.36),rgba(26,40,58,.86));box-shadow:0 12px 28px rgba(0,0,0,.14);transition:transform .25s ease,border-color .25s ease,box-shadow .25s ease}
      .manja-banner:active{transform:scale(.985)}.manja-banner.hidden{display:none}.manja-banner-left{display:flex;gap:10px;align-items:center;min-width:0}.manja-orb{width:39px;height:39px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#ffcc4d,#f39a18);box-shadow:0 0 20px rgba(255,180,36,.22);font-size:19px}.manja-copy strong{display:block;font-size:12px}.manja-copy small{display:block;color:#a9b6c8;font-size:9px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.manja-count{min-width:32px;height:28px;padding:0 9px;border-radius:999px;display:grid;place-items:center;background:rgba(255,193,44,.13);border:1px solid rgba(255,193,44,.28);color:#ffd169;font-weight:900;font-size:12px}
      .mini-order.manja-order{border-color:rgba(255,190,47,.42)!important;background:linear-gradient(180deg,rgba(53,42,18,.42),rgba(10,24,40,.98))!important;box-shadow:0 10px 26px rgba(255,174,32,.06)}.manja-chip{display:inline-flex;align-items:center;gap:5px;margin:0 0 7px;padding:5px 8px;border-radius:999px;background:rgba(255,191,38,.12);border:1px solid rgba(255,191,38,.28);color:#ffd169;font-size:9px;font-weight:900;letter-spacing:.04em}
      .manja-section-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:2px 0 10px}.manja-section-title strong{font-size:13px}.manja-section-title span{font-size:9px;color:#ffd169}
    `;
    document.head.appendChild(style);
  }

  function ensureBanner(){
    ensureStyles();
    const page=$('#ordersPage'); if(!page) return null;
    let banner=$('#manjaBanner');
    if(!banner){
      banner=document.createElement('button');
      banner.id='manjaBanner';
      banner.className='manja-banner hidden';
      banner.type='button';
      banner.innerHTML='<span class="manja-banner-left"><span class="manja-orb">📅</span><span class="manja-copy"><strong>MANJA • Manajemen Janji</strong><small>Ada janji pelanggan yang perlu diperhatikan</small></span></span><span class="manja-count">0</span>';
      const anchor=$('#myOrderSummary',page) || $('#myOrdersList',page);
      anchor?.parentNode?.insertBefore(banner,anchor);
      banner.addEventListener('click',()=>renderManjaOnly());
    }
    return banner;
  }

  function updateBanner(){
    const rows=allManja(window.state?.myOpenOrders || state?.myOpenOrders);
    const banner=ensureBanner(); if(!banner) return;
    banner.classList.toggle('hidden',rows.length===0);
    $('.manja-count',banner).textContent=String(rows.length);
    const small=$('.manja-copy small',banner);
    if(small) small.textContent=rows.length ? `${rows.length} order berstatus MANJA • ketuk untuk lihat` : 'Tidak ada MANJA aktif';
    if(rows.length && !sessionStorage.getItem('manja-reminded')){
      sessionStorage.setItem('manja-reminded','1');
      try{ window.showToast?.(`📅 Kamu punya ${rows.length} MANJA aktif`); }catch(_){ }
    }
  }

  function decorateVisibleOrders(){
    const data=window.state?.myOpenOrders || state?.myOpenOrders;
    const map=new Map(allManja(data).map(o=>[String(o.service_number||''),o]));
    $$('#myOrdersList .mini-order').forEach(card=>{
      const text=card.textContent||'';
      const found=[...map.entries()].find(([inet])=>inet && text.includes(inet));
      if(!found) return;
      const [,order]=found;
      card.classList.add('manja-order');
      if(!$('.manja-chip',card)){
        const chip=document.createElement('div'); chip.className='manja-chip'; chip.textContent='📅 MANJA'; card.prepend(chip);
      }
      const ket=order.keterangan || order.rca_detail || order.note || order.notes || '';
      if(ket && !card.textContent.includes(ket)){
        const small=$('small',card); if(small) small.insertAdjacentHTML('beforeend',`<br>🗓️ MANJA: ${escHtml(ket)}`);
      }
    });
  }

  function renderManjaOnly(){
    const data=window.state?.myOpenOrders || state?.myOpenOrders;
    const rows=allManja(data);
    const list=$('#myOrdersList'), count=$('#myOrderCount');
    if(!list) return;
    list.replaceChildren();
    if(count) count.textContent=`${rows.length} MANJA`;
    const back=document.createElement('button');
    back.className='tool-action'; back.innerHTML='<b>‹ Kembali ke semua order</b><span>📅</span>';
    back.addEventListener('click',()=>{ if(typeof window.renderMyOrderAreas==='function') window.renderMyOrderAreas(data); else renderMyOrderAreas(data); });
    list.appendChild(back);
    const title=document.createElement('div'); title.className='manja-section-title'; title.innerHTML=`<strong>📅 MANJA AKTIF</strong><span>${rows.length} order</span>`; list.appendChild(title);
    if(!rows.length){list.insertAdjacentHTML('beforeend','<div class="empty"><p>Tidak ada MANJA aktif.</p></div>');return;}
    rows.forEach((o,i)=>{
      const card=document.createElement('div'); card.className='mini-order manja-order';
      const ket=o.keterangan || o.rca_detail || o.note || o.notes || '-';
      card.innerHTML=`<div class="manja-chip">📅 MANJA</div><strong>${i+1}. ${escHtml(o.customer_name||'-')}</strong><small style="line-height:1.7">🌐 ${escHtml(o.service_number||'-')}<br>🎫 ${escHtml(o.ticket_id||'MANUAL')}<br>📍 ${escHtml(o.__area||'-')}<br>📞 ${escHtml(o.customer_phone||'-')}<br>📡 ONU RX: ${escHtml(o.onu_rx||'-')}<br>📝 ${escHtml(ket)}<br>🏠 ${escHtml(o.address||'-')}</small>`;
      list.appendChild(card);
    });
  }

  function wrapRenderer(name){
    const original=window[name];
    if(typeof original!=='function' || original.__manjaWrapped) return;
    const wrapped=function(...args){ const out=original.apply(this,args); queueMicrotask(()=>{updateBanner();decorateVisibleOrders();}); return out; };
    wrapped.__manjaWrapped=true; window[name]=wrapped;
  }

  function init(){
    ensureBanner();
    wrapRenderer('renderMyOrderAreas');
    wrapRenderer('renderMyOpenArea');
    updateBanner(); decorateVisibleOrders();
    const observer=new MutationObserver(()=>{updateBanner();decorateVisibleOrders();});
    const list=$('#myOrdersList'); if(list) observer.observe(list,{childList:true,subtree:true});
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true}); else init();
})();
