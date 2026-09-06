// Orderanku area filter: keep operational areas broad, never break orders down by street.
(function(){
  'use strict';
  if(typeof renderMyOrderAreas!=='function') return;

  const _renderMyOrderAreas=renderMyOrderAreas;

  function operationalArea(address){
    const text=String(address||'').toUpperCase().replace(/[^A-Z0-9 ]+/g,' ').replace(/\s+/g,' ').trim();
    if(text.includes('NGINDEN')) return 'NGINDEN';
    if(text.includes('SEMOLO')) return 'SEMOLO';
    if(text.includes('JAGIR')) return 'JAGIR';
    return 'LAINNYA';
  }

  function groupAreas(payload){
    const map=new Map();
    (payload?.areas||[]).forEach(sourceArea=>{
      (sourceArea.orders||[]).forEach(order=>{
        const area=operationalArea(order.address);
        if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
        const group=map.get(area);
        group.open++;
        group.orders.push({...order,area});
      });
      // Preserve status totals even when an area currently has no OPEN order.
      if(!(sourceArea.orders||[]).length){
        const area=String(sourceArea.area||'LAINNYA').toUpperCase();
        if(['NGINDEN','SEMOLO','JAGIR'].includes(area)){
          if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
          const group=map.get(area);
          group.close+=Number(sourceArea.close||0);
          group.update+=Number(sourceArea.update||0);
        }
      }
    });

    const priority=['NGINDEN','SEMOLO','JAGIR','LAINNYA'];
    return Array.from(map.values()).sort((a,b)=>priority.indexOf(a.area)-priority.indexOf(b.area));
  }

  window.renderMyOrderAreas=function renderMyOrderAreasOperational(payload){
    const grouped={...payload,areas:groupAreas(payload)};
    // Do not expose street names as area buttons; clicking an area still shows all orders.
    return _renderMyOrderAreas(grouped);
  };

  window.KerjaBotOrderArea={operationalArea,groupAreas};
})();
