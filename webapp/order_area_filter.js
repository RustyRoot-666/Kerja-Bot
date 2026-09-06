// Orderanku: direct area listing.
// Show the actual operational areas returned by the backend.
// Do not collapse areas into NGINDEN / SEMOLO / JAGIR / LAINNYA.
(function(){
  'use strict';
  if(window.__KerjaBotDirectAreaFilter) return;
  window.__KerjaBotDirectAreaFilter=true;

  const clean=v=>String(v||'').toUpperCase()
    .replace(/[^A-Z0-9\s-]+/g,' ')
    .replace(/\s+/g,' ').trim();

  function areaName(source){
    return clean(source?.area || 'LAINNYA') || 'LAINNYA';
  }

  function groupPayload(payload){
    const map=new Map();
    (payload?.areas||[]).forEach(source=>{
      const area=areaName(source);
      if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
      const group=map.get(area);
      group.open+=Number(source.open||0);
      group.close+=Number(source.close||0);
      group.update+=Number(source.update||0);
      (source.orders||[]).forEach(order=>group.orders.push({...order,area}));
    });

    // Keep the same order as the API where possible.
    return [...map.values()];
  }

  function escapeHtml(v){
    return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function renderDirect(payload){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return false;

    const groups=groupPayload(payload);
    list.replaceChildren();
    if(count) count.textContent=`${Number(payload?.total_open||0)} OPEN`;

    if(!groups.length){
      list.innerHTML='<div class="empty"><p>✅ Tidak ada order OPEN dari Google Sheets.</p></div>';
      return true;
    }

    groups.forEach(group=>{
      const b=document.createElement('button');
      b.type='button';
      b.className='tool-action';
      b.dataset.directArea=group.area;
      const detail=[];
      detail.push(`🟢 Open: ${group.open}`);
      if(group.close) detail.push(`🔴 Close: ${group.close}`);
      if(group.update) detail.push(`🟡 Update: ${group.update}`);
      b.innerHTML=`<div><b>📍 ${escapeHtml(group.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">${detail.join(' | ')}</small></div><span>${group.open} ›</span>`;
      b.addEventListener('click',()=>{
        if(typeof renderMyOpenArea==='function') renderMyOpenArea(group);
        else showDirectOrders(group);
      });
      list.appendChild(b);
    });

    list.dataset.directAreaDetail='0';
    return true;
  }

  function showDirectOrders(group){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return;
    list.replaceChildren();
    if(count) count.textContent=`${group.orders.length} OPEN`;

    const back=document.createElement('button');
    back.type='button';
    back.className='tool-action';
    back.innerHTML=`<b>‹ Kembali ke daftar area</b><span>📍 ${escapeHtml(group.area)}</span>`;
    back.addEventListener('click',()=>renderDirect(window.__KerjaBotMyOpenPayload || (typeof state!=='undefined'?state.myOpenOrders:null)));
    list.appendChild(back);

    group.orders.forEach((o,i)=>{
      const c=document.createElement('div');
      c.className='mini-order';
      c.innerHTML=`<strong>${i+1}. ${escapeHtml(o.customer_name||'-')}</strong><small style="line-height:1.65">🎫 ${escapeHtml(o.ticket_id||'MANUAL')}<br>🌐 ${escapeHtml(o.service_number||'-')}<br>📞 ${escapeHtml(o.customer_phone||'-')}<br>⚡ ${escapeHtml(o.package||'-')}<br>📡 ONU RX: ${escapeHtml(o.onu_rx||'-')}<br>📝 RCA: ${escapeHtml(o.rca||'-')}<br>🏠 ${escapeHtml(o.address||'-')}</small>`;
      list.appendChild(c);
    });
    list.dataset.directAreaDetail='1';
  }

  function payload(){
    return window.__KerjaBotMyOpenPayload || (typeof state!=='undefined' ? state.myOpenOrders : null);
  }

  function hookLoader(){
    if(typeof window.loadMyOpenOrders!=='function') return false;
    if(window.loadMyOpenOrders.__directAreaHooked) return true;
    const original=window.loadMyOpenOrders;
    const wrapped=async function(force){
      const result=await original(force);
      const d=(typeof state!=='undefined' ? state.myOpenOrders : null)||result;
      if(d){
        window.__KerjaBotMyOpenPayload=d;
        setTimeout(()=>renderDirect(d),0);
      }
      return result;
    };
    wrapped.__directAreaHooked=true;
    window.loadMyOpenOrders=wrapped;
    return true;
  }

  function observeList(){
    const list=document.querySelector('#myOrdersList');
    if(!list || list.__directAreaObserver) return;
    list.__directAreaObserver=true;
    new MutationObserver(()=>{
      if(list.dataset.directAreaRendering==='1') return;
      // If another renderer paints the area buttons, restore the backend area list.
      if(list.querySelector('.order-area-btn') && !list.dataset.directAreaDetail){
        const d=payload();
        if(d){
          list.dataset.directAreaRendering='1';
          renderDirect(d);
          list.dataset.directAreaRendering='0';
        }
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
    setTimeout(()=>{
      const d=payload();
      if(d) renderDirect(d);
    },500);
  });

  window.KerjaBotOrderArea={groupPayload,renderDirect,showDirectOrders};
})();