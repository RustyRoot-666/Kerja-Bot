(()=>{
const esc=v=>String(v??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));
const cacheKey=a=>'kerja-bot-geo:'+a.trim().toLowerCase().replace(/\s+/g,' ');
let opening=null;
function loadLeaflet(){return new Promise((resolve,reject)=>{if(window.L)return resolve();const css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(css);const s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=resolve;s.onerror=reject;document.head.appendChild(s)})}
function styles(){if(document.getElementById('zoneMapStyles'))return;const s=document.createElement('style');s.id='zoneMapStyles';s.textContent=`#zoneMapStage{position:relative;height:100%;min-height:420px;background:#071018}#zoneMapCanvas{position:absolute;inset:0}.zone-panel{position:absolute;z-index:900;right:14px;top:14px;width:280px;max-height:calc(100% - 28px);overflow:auto;background:rgba(5,10,15,.92);border:1px solid rgba(92,224,255,.25);backdrop-filter:blur(10px);padding:14px}.zone-panel h3{margin:0 0 8px;font:700 20px 'Barlow Condensed',sans-serif;letter-spacing:.08em}.zone-stat{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08);font-size:12px}.zone-item{padding:10px 0;border-bottom:1px solid rgba(255,255,255,.08);cursor:pointer}.zone-item b{display:block;font-size:13px}.zone-item small{opacity:.65}.zone-label{background:rgba(5,10,15,.9);color:#5ce0ff;border:1px solid rgba(92,224,255,.45);font:700 12px 'Barlow Condensed';padding:3px 6px}.zone-sync{margin-top:10px;width:100%;padding:8px;border:1px solid rgba(92,224,255,.3);background:transparent;color:#5ce0ff;cursor:pointer}.leaflet-popup-content{font-family:Inter,sans-serif;font-size:12px}.leaflet-control-attribution{font-size:9px}@media(max-width:700px){.zone-panel{left:10px;right:10px;top:10px;width:auto;max-height:180px}.zone-item{display:inline-block;width:48%;vertical-align:top}}`;document.head.appendChild(s)}
function getOrders(){return fetch('/api/web/open-orders',{credentials:'same-origin'}).then(r=>{if(!r.ok)throw Error('Order API '+r.status);return r.json()}).then(o=>{const items=[];(o.areas||[]).forEach(a=>(a.orders||[]).forEach(x=>items.push(x)));return items})}
async function geocode(address){const k=cacheKey(address);try{const old=JSON.parse(localStorage.getItem(k)||'null');if(old&&Number.isFinite(old.lat)&&Number.isFinite(old.lng))return old}catch{}const url='https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=id&q='+encodeURIComponent(address+', Surabaya, Jawa Timur, Indonesia');try{const r=await fetch(url,{headers:{Accept:'application/json'}});const d=await r.json();if(d&&d[0]){const out={lat:+d[0].lat,lng:+d[0].lon,name:d[0].display_name||''};if(Number.isFinite(out.lat)&&Number.isFinite(out.lng)){localStorage.setItem(k,JSON.stringify(out));return out}}}catch(e){console.warn('geocode',address,e)}return null}
function zoneKey(lat,lng){return `${Math.floor(lat/.001)*.001},${Math.floor(lng/.001)*.001}`}
async function openZoneMap(){
  if(opening)return opening;
  opening=(async()=>{
    styles();await loadLeaflet();
    const stage=document.querySelector('.map-stage');if(!stage)return;
    if(stage.dataset.zoneReady==='1'){const canvas=document.getElementById('zoneMapCanvas');if(canvas&&canvas._leaflet_id){return}stage.dataset.zoneReady='0'}
    stage.innerHTML='<div id="zoneMapStage"><div id="zoneMapCanvas"></div><div class="zone-panel"><h3>CUSTOMER ZONES</h3><div class="zone-stat"><span>GEOCODED</span><b id="zg">0</b></div><div class="zone-stat"><span>ZONES</span><b id="zz">0</b></div><div class="zone-stat"><span>CUSTOMERS</span><b id="zc">0</b></div><div id="zoneList"></div><button class="zone-sync" id="zoneSync">SYNC ALAMAT</button></div></div>';
    const map=L.map('zoneMapCanvas',{zoomControl:true}).setView([-7.27,112.75],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(map);const customerLayer=L.layerGroup().addTo(map),zoneLayer=L.layerGroup().addTo(map);
    stage.dataset.zoneReady='1';
    async function refresh(sync=false){
      const orders=await getOrders();const groups={};let geocoded=0;const unique=[...new Map(orders.map(o=>[String(o.address||'').trim(),o])).values()].filter(o=>o.address);
      if(sync){for(const o of unique){if(geocoded>=5)break;const k=cacheKey(o.address);if(localStorage.getItem(k))continue;await geocode(o.address);geocoded++;await new Promise(r=>setTimeout(r,1100))}}
      customerLayer.clearLayers();zoneLayer.clearLayers();const customers=[];
      for(const o of orders){const address=String(o.address||'').trim();let g=null;try{g=JSON.parse(localStorage.getItem(cacheKey(address))||'null')}catch{}if(!g||!Number.isFinite(+g.lat)||!Number.isFinite(+g.lng))continue;const lat=+g.lat,lng=+g.lng;const zk=zoneKey(lat,lng);if(!groups[zk])groups[zk]={id:'Z'+String(Object.keys(groups).length+1).padStart(2,'0'),lat:0,lng:0,total:0,open:0};const z=groups[zk];z.lat+=lat;z.lng+=lng;z.total++;z.open++;customers.push({...o,latitude:lat,longitude:lng,zone_id:z.id)}
      }
      Object.values(groups).forEach(z=>{z.latitude=z.lat/z.total;z.longitude=z.lng/z.total;L.marker([z.latitude,z.longitude],{icon:L.divIcon({className:'zone-label',html:'ZONE '+esc(z.id),iconSize:null})}).bindPopup('<b>ZONE '+esc(z.id)+'</b><br>Customer: '+z.total+'<br>Open: '+z.open).addTo(zoneLayer)});
      customers.forEach(c=>L.circleMarker([c.latitude,c.longitude],{radius:5,weight:2,fillOpacity:.8}).bindPopup('<b>'+esc(c.customer_name||'-')+'</b><br>'+esc(c.service_number||'-')+'<br>'+esc(c.address||'-')+'<br><b>'+esc(c.zone_id)+'</b>').addTo(customerLayer));
      const zg=document.getElementById('zg'),zz=document.getElementById('zz'),zc=document.getElementById('zc'),list=document.getElementById('zoneList');
      if(!zg||!zz||!zc||!list||!document.getElementById('zoneMapCanvas'))return;
      zg.textContent=orders.length?customers.length:0;zz.textContent=Object.keys(groups).length;zc.textContent=customers.length;
      list.innerHTML=Object.values(groups).map(z=>'<div class="zone-item" data-lat="'+z.latitude+'" data-lng="'+z.longitude+'"><b>ZONE '+esc(z.id)+'</b><small>'+z.total+' customer • '+z.open+' open</small></div>').join('')||'<p class="muted">Belum ada koordinat. Tekan SYNC ALAMAT.</p>';
      document.querySelectorAll('.zone-item').forEach(el=>el.onclick=()=>map.setView([+el.dataset.lat,+el.dataset.lng],16));
      if(customers.length){const b=L.latLngBounds(customers.map(c=>[c.latitude,c.longitude]));map.fitBounds(b,{padding:[30,30],maxZoom:15})}
    }
    const sync=document.getElementById('zoneSync');if(sync)sync.onclick=async()=>{sync.disabled=true;sync.textContent='GEOCODING...';try{await refresh(true)}finally{sync.disabled=false;sync.textContent='SYNC ALAMAT'}};
    await refresh(false);setInterval(()=>refresh(false).catch(console.warn),60000);window.KerjaBotCustomerZones={refresh};
  })();
  try{return await opening}finally{opening=null}
}
window.KerjaBotOpenZoneMap=openZoneMap;
const boot=()=>{const stage=document.querySelector('.map-stage');if(stage&&!stage.dataset.zoneBooted){stage.dataset.zoneBooted='1';openZoneMap().catch(console.error)}};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else setTimeout(boot,300);
})();
