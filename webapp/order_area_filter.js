// Orderanku: broad operational area grouping.
// IMPORTANT: do not break orders down by street.
(function(){
  'use strict';
  if(window.__KerjaBotBroadAreaFilter) return;
  window.__KerjaBotBroadAreaFilter=true;

  const clean=v=>String(v||'').toUpperCase()
    .replace(/[^A-Z0-9\s-]+/g,' ')
    .replace(/\s+/g,' ').trim();

  function operationalArea(order){
    const raw=clean(order?.address||'');
    const existing=clean(order?.area||'');
    if(existing==='NGINDEN'||existing==='SEMOLO'||existing==='JAGIR') return existing;
    if(/\bJAGIR\b|\bJGR\b/.test(raw)) return 'JAGIR';
    if(/\bNGINDEN\b|NGINDEN JANGKUNGAN|NGINDEN SEMOLO|NGINDEN INTAN|NGINDEN BARU/.test(raw)) return 'NGINDEN';
    if(/\bSEMOLO\b|SEMOLOWARU|KEPUTIH|BUMI MARINA|MEDOKAN SEMAMPIR|KLAMPIS NGASEM|MENUR PUMPUNGAN|GEBANG PUTIH/.test(raw)) return 'SEMOLO';
    return 'LAINNYA';
  }

  function groupPayload(payload){
    const map=new Map();
    (payload?.areas||[]).forEach(source=>{
      (source.orders||[]).forEach(order=>{
        const area=operationalArea(order);
        if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
        const group=map.get(area);
        group.open++;
        group.orders.push({...order,area});
      });
      if(!(source.orders||[]).length){
        const area=clean(source.area);
        if(['NGINDEN','SEMOLO','JAGIR'].includes(area)){
          if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
          const group=map.get(area);
          group.close+=Number(source.close||0);
          group.update+=Number(source.update||0);
        }
      }
    });
    const priority=['NGINDEN','SEMOLO','JAGIR','LAINNYA'];
    return Array.from(map.values()).sort((a,b)=>priority.indexOf(a.area)-priority.indexOf(b.area));
  }

  function escapeHtml(v){
    return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function renderBroad(payload){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return false;
    const grouped=groupPayload(payload);
    list.replaceChildren();
    if(count) count.textContent=`${Number(payload?.total_open||0)} data`;
    if(!grouped.length){list.innerHTML='<div class="empty"><p>✅ Tidak ada order OPEN dari Google Sheets.</p></div>';return true;}

    grouped.forEach(group=>{
      const b=document.createElement('button');
      b.type='button';
      b.className='tool-action';
      b.dataset.operationalArea=group.area;
      b.innerHTML=`<div><b>📍 ${escapeHtml(group.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${group.open}${group.close?` | 🔴 Close: ${group.close}`:''}${group.update?` | 🟡 Update: ${group.update}`:''}</small></div><span>${group.open} ›</span>`;
      b.addEventListener('click',()=>showBroadOrders(group));
      list.appendChild(b);
    });
    list.dataset.broadAreaDetail='0';
    return true;
  }

  function showBroadOrders(group){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return;
    list.dataset.broadAreaDetail='1';
    list.replaceChildren();
    if(count) count.textContent=`${group.orders.length} OPEN`;
    const back=document.createElement('button');
    back.type='button';
    back.className='tool-action';
    back.innerHTML='<b>‹ Kembali ke daftar area</b><span>📍</span>';
    back.addEventListener('click',()=>renderBroad(window.__KerjaBotMyOpenPayload || (typeof state!=='undefined'?state.myOpenOrders:null)));
    list.appendChild(back);
    group.orders.forEach((o,i)=>{
      const c=document.createElement('div');
      c.className='mini-order';
      c.innerHTML=`<strong>${i+1}. ${escapeHtml(o.customer_name||'-')}</strong><small style="line-height:1.65">🎫 ${escapeHtml(o.ticket_id||'MANUAL')}<br>🌐 ${escapeHtml(o.service_number||'-')}<br>📞 ${escapeHtml(o.customer_phone||'-')}<br>⚡ ${escapeHtml(o.package||'-')}<br>📡 ONU RX: ${escapeHtml(o.onu_rx||'-')}<br>📝 RCA: ${escapeHtml(o.rca||'-')}<br>🏠 ${escapeHtml(o.address||'-')}</small>`;
      list.appendChild(c);
    });
  }

  function payload(){
    return window.__KerjaBotMyOpenPayload || (typeof state!=='undefined' ? state.myOpenOrders : null);
  }

  function hookLoader(){
    if(typeof window.loadMyOpenOrders!=='function') return false;
    if(window.loadMyOpenOrders.__broadAreaHooked) return true;
    const original=window.loadMyOpenOrders;
    const wrapped=async function(force){
      const result=await original(force);
      const d=(typeof state!=='undefined' ? state.myOpenOrders : null)||result;
      if(d){window.__KerjaBotMyOpenPayload=d;setTimeout(()=>renderBroad(d),0);}
      return result;
    };
    wrapped.__broadAreaHooked=true;
    window.loadMyOpenOrders=wrapped;
    return true;
  }

  function observeList(){
    const list=document.querySelector('#myOrdersList');
    if(!list || list.__broadAreaObserver) return;
    list.__broadAreaObserver=true;
    new MutationObserver(()=>{
      const d=payload();
      if(!d || list.dataset.broadAreaDetail==='1') return;
      if(list.dataset.broadAreaRendering==='1') return;
      if(list.querySelector('.mini-order')){
        list.dataset.broadAreaRendering='1';
        renderBroad(d);
        list.dataset.broadAreaRendering='0';
      }
    }).observe(list,{childList:true,subtree:true});
  }

  let tries=0;
  const timer=setInterval(()=>{
    observeList();
    if(hookLoader() || ++tries>80) clearInterval(timer);
  },250);

  document.addEventListener('DOMContentLoaded',()=>{
    observeList();
    hookLoader();
    setTimeout(()=>{const d=payload();if(d){window.__KerjaBotMyOpenPayload=d;renderBroad(d);}},500);
  });

  window.KerjaBotOrderArea={operationalArea,groupPayload,renderBroad,showBroadOrders};
})();