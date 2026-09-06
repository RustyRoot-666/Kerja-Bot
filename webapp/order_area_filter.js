// Orderanku area filter: keep operational areas broad, never break orders down by street.
(function(){
  'use strict';
  if(typeof renderMyOrderAreas!=='function') return;

  const _renderMyOrderAreas=renderMyOrderAreas;

  function operationalArea(order){
    const text=String(order?.address||'').toUpperCase().replace(/[^A-Z0-9 ]+/g,' ').replace(/\s+/g,' ').trim();
    const existing=String(order?.area||'').toUpperCase().trim();
    if(existing==='NGINDEN'||existing==='SEMOLO'||existing==='JAGIR') return existing;
    if(text.includes('JAGIR')) return 'JAGIR';
    if(/\bNGINDEN\b|NGINDEN JANGKUNGAN|NGINDEN SEMOLO|NGINDEN INTAN|NGINDEN BARU/.test(text)) return 'NGINDEN';
    if(/\bSEMOLO\b|SEMOLOWARU|KEPUTIH|BUMI MARINA|MEDOKAN SEMAMPIR|KLAMPIS NGASEM|MENUR PUMPUNGAN|GEBANG PUTIH/.test(text)) return 'SEMOLO';
    return 'LAINNYA';
  }

  function groupAreas(payload){
    const map=new Map();
    (payload?.areas||[]).forEach(sourceArea=>{
      (sourceArea.orders||[]).forEach(order=>{
        const area=operationalArea(order);
        if(!map.has(area)) map.set(area,{area,open:0,close:0,update:0,orders:[]});
        const group=map.get(area);
        group.open++;
        group.orders.push({...order,area});
      });
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
    return _renderMyOrderAreas(grouped);
  };

  window.KerjaBotOrderArea={operationalArea,groupAreas};

  // workflow_area.js loads this file dynamically. If Orderanku already loaded
  // before this override arrived, immediately repaint it with the area groups.
  if(typeof state!=='undefined' && state.myOpenOrders) setTimeout(()=>renderMyOrderAreas(state.myOpenOrders),0);
})();
