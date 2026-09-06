// Orderanku address categories: group orders by the customer's street/address family.
// Example: "NGINDEN 1 20" + "NGINDEN BARU 2 30" => NGINDEN.
// Other addresses use the street name before the first house/gang number.
(function(){
  'use strict';
  if(typeof renderMyOrderAreas!=='function') return;

  const _renderMyOrderAreas=renderMyOrderAreas;

  const CITY_WORDS=new Set(['SBY','SURABAYA','JAWA','TIMUR','INDONESIA']);

  function normalizeAddress(value){
    return String(value||'')
      .toUpperCase()
      .replace(/[^A-Z0-9 ]+/g,' ')
      .replace(/\s+/g,' ')
      .trim();
  }

  function addressCategory(order){
    const text=normalizeAddress(order?.address);
    if(!text) return 'ALAMAT LAINNYA';

    const tokens=text.split(' ').filter(Boolean);

    // Operational naming rule: every NGINDEN variant belongs to NGINDEN.
    // This intentionally merges NGINDEN, NGINDEN BARU, NGINDEN JANGKUNGAN,
    // NGINDEN SEMOLO, etc. into one customer-address category.
    if(tokens[0]==='NGINDEN') return 'NGINDEN';

    // Remove trailing city/region words, then stop at the first numeric token.
    const street=[];
    for(const token of tokens){
      if(/^\d+$/.test(token)) break;
      if(CITY_WORDS.has(token)) break;
      street.push(token);
    }

    // A malformed address may contain only a number or city name.
    if(!street.length) return 'ALAMAT LAINNYA';

    return street.join(' ');
  }

  function groupAreas(payload){
    const map=new Map();

    (payload?.areas||[]).forEach(sourceArea=>{
      (sourceArea.orders||[]).forEach(order=>{
        const area=addressCategory(order);
        if(!map.has(area)){
          map.set(area,{area,open:0,close:0,update:0,orders:[]});
        }
        const group=map.get(area);
        group.open++;
        group.orders.push({...order,area});
      });

      // Preserve summary counts for source groups that have no order rows.
      if(!(sourceArea.orders||[]).length){
        const area=String(sourceArea.area||'').toUpperCase().trim();
        if(area && !map.has(area)){
          map.set(area,{area,open:0,close:Number(sourceArea.close||0),update:Number(sourceArea.update||0),orders:[]});
        }else if(area){
          const group=map.get(area);
          group.close+=Number(sourceArea.close||0);
          group.update+=Number(sourceArea.update||0);
        }
      }
    });

    return Array.from(map.values()).sort((a,b)=>{
      if(a.area==='NGINDEN') return -1;
      if(b.area==='NGINDEN') return 1;
      return a.area.localeCompare(b.area,'id');
    });
  }

  window.renderMyOrderAreas=function renderMyOrderAreasByAddress(payload){
    const grouped={...payload,areas:groupAreas(payload)};
    return _renderMyOrderAreas(grouped);
  };

  window.KerjaBotOrderArea={normalizeAddress,addressCategory,groupAreas};

  // workflow_area.js loads this file dynamically. If Orderanku already loaded
  // before this override arrived, immediately repaint it with the new categories.
  if(typeof state!=='undefined' && state.myOpenOrders){
    setTimeout(()=>renderMyOrderAreas(state.myOpenOrders),0);
  }
})();
