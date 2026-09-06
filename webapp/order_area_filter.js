// Orderanku: group OPEN orders by customer address category.
// Example: NGINDEN 1 20 + NGINDEN BARU 2 30 => NGINDEN.
(function(){
  'use strict';
  if(window.__KerjaBotAddressAreaFilter) return;
  window.__KerjaBotAddressAreaFilter=true;

  const clean=v=>String(v||'').toUpperCase()
    .replace(/\bNO\.?\s*\d+[A-Z]?\b/g,' ')
    .replace(/[^A-Z0-9\s-]+/g,' ')
    .replace(/\s+/g,' ').trim();

  function addressCategory(address){
    const raw=clean(address);
    if(!raw) return 'ALAMAT LAINNYA';

    // NGINDEN family is intentionally one category.
    if(/^NGINDEN(?:\s|$)/.test(raw)) return 'NGINDEN';

    // Keep common compound street names intact.
    const known=[
      'BUMI MARINA MAS TIMUR','BUMI MARINA MAS','KEDUNG TARUKAN BARU',
      'KEDUNG TARUKAN','KARANG MENJANGAN','JOJORAN','SEMOLOWARU',
      'MENUR PUMPUNGAN','MEDOKAN SEMAMPIR','KLAMPIS NGASEM','GEBANG PUTIH',
      'KEPUTIH','RUNGKUT','GUNUNG ANYAR','MERR','KALIDAMI','NGAGEL',
      'DARMAWANGSA','MANYAR','JAGIR'
    ];
    const hit=known.find(name=>raw===name || raw.startsWith(name+' '));
    if(hit) return hit;

    // Generic rule: category is the address/street name before the first number.
    const m=raw.match(/^(.+?)\s+\d+(?:[A-Z])?(?:\s|$)/);
    if(m?.[1]) return m[1].trim();

    const parts=raw.split(/\s+/);
    while(parts.length && /^\d+[A-Z]?(?:-[A-Z0-9]+)?$/.test(parts[parts.length-1])) parts.pop();
    return parts.join(' ')||'ALAMAT LAINNYA';
  }

  function groupPayload(payload){
    const groups=new Map();
    (payload?.areas||[]).forEach(source=>{
      (source.orders||[]).forEach(order=>{
        const area=addressCategory(order.address);
        if(!groups.has(area)) groups.set(area,{area,open:0,close:0,update:0,orders:[]});
        const g=groups.get(area);
        g.open++;
        g.orders.push({...order,area});
      });
    });
    return Array.from(groups.values()).sort((a,b)=>a.area.localeCompare(b.area,'id'));
  }

  function escapeHtml(v){
    return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function renderGrouped(payload){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return false;
    const grouped=groupPayload(payload);
    list.replaceChildren();
    if(count) count.textContent=`${payload?.total_open||grouped.reduce((n,g)=>n+g.open,0)} OPEN`;
    if(!grouped.length){list.innerHTML='<div class="empty"><p>✅ Tidak ada order OPEN dari Google Sheets.</p></div>';return true;}

    grouped.forEach(group=>{
      const b=document.createElement('button');
      b.type='button';
      b.className='tool-action';
      b.dataset.addressArea=group.area;
      b.innerHTML=`<div><b>📍 ${escapeHtml(group.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${group.open}</small></div><span>${group.open} ›</span>`;
      b.addEventListener('click',()=>showCategory(group));
      list.appendChild(b);
    });
    list.dataset.addressCategoryDetail='0';
    return true;
  }

  function showCategory(group){
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!list) return;
    list.dataset.addressCategoryDetail='1';
    list.replaceChildren();
    if(count) count.textContent=`${group.orders.length} OPEN`;

    const back=document.createElement('button');
    back.type='button'; back.className='tool-action';
    back.innerHTML='<b>‹ Kembali ke daftar alamat</b><span>📍</span>';
    back.addEventListener('click',()=>renderGrouped(window.__KerjaBotMyOpenPayload));
    list.appendChild(back);

    group.orders.forEach((o,i)=>{
      const c=document.createElement('div'); c.className='mini-order';
      c.innerHTML=`<strong>${i+1}. ${escapeHtml(o.customer_name||'-')}</strong><small style="line-height:1.65">🎫 ${escapeHtml(o.ticket_id||'MANUAL')}<br>🌐 ${escapeHtml(o.service_number||'-')}<br>📞 ${escapeHtml(o.customer_phone||'-')}<br>⚡ ${escapeHtml(o.package||'-')}<br>📡 ONU RX: ${escapeHtml(o.onu_rx||'-')}<br>📝 RCA: ${escapeHtml(o.rca||'-')}<br>🏠 ${escapeHtml(o.address||'-')}</small>`;
      list.appendChild(c);
    });
  }

  function currentPayload(){
    return window.__KerjaBotMyOpenPayload || (typeof state!=='undefined' ? state.myOpenOrders : null);
  }

  // Hook the real loader. This fixes the previous problem where overriding the
  // renderer could be bypassed by app.js's lexical function binding.
  function hookLoader(){
    if(typeof window.loadMyOpenOrders!=='function') return false;
    if(window.loadMyOpenOrders.__addressCategoryHooked) return true;
    const original=window.loadMyOpenOrders;
    const wrapped=async function(force){
      const result=await original(force);
      const payload=(typeof state!=='undefined' ? state.myOpenOrders : null)||result;
      if(payload){window.__KerjaBotMyOpenPayload=payload;setTimeout(()=>renderGrouped(payload),0);}
      return result;
    };
    wrapped.__addressCategoryHooked=true;
    window.loadMyOpenOrders=wrapped;
    return true;
  }

  let tries=0;
  const timer=setInterval(()=>{if(hookLoader()||++tries>80)clearInterval(timer);},250);

  // Catch the initial direct order-card render even if the loader was called
  // before this script finished installing its wrapper.
  function observeList(){
    const list=document.querySelector('#myOrdersList');
    if(!list || list.__addressObserver) return;
    list.__addressObserver=true;
    new MutationObserver(()=>{
      const payload=currentPayload();
      if(!payload || list.dataset.addressCategoryDetail==='1') return;
      if(list.dataset.addressCategoryRendering==='1') return;
      if(list.querySelector('.mini-order')){
        list.dataset.addressCategoryRendering='1';
        renderGrouped(payload);
        list.dataset.addressCategoryRendering='0';
      }
    }).observe(list,{childList:true,subtree:true});
  }

  document.addEventListener('DOMContentLoaded',()=>{observeList();hookLoader();setTimeout(()=>{const p=currentPayload();if(p){window.__KerjaBotMyOpenPayload=p;renderGrouped(p);}},500);});
  setTimeout(observeList,1000);

  window.KerjaBotOrderAddress={addressCategory,groupPayload,renderGrouped,showCategory};
})();
