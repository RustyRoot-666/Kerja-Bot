let areaMap=null;
let areaLayer=null;
let areaPolygonLayer=null;

// STO MYR service territory confirmed from the MYR replacement-order dataset.
// The public Area Success Map must show ONLY these kecamatan.
const MYR_KECAMATAN = new Set(['SUKOLILO','MULYOREJO','GUBENG','TAMBAKSARI','TENGGILIS MEJOYO','RUNGKUT']);
const SURABAYA_KECAMATAN_GEOJSON = 'https://cdn.jsdelivr.net/gh/rizalmaulanaairlangga/backend-health-facility-gis-surabaya@157cc75d34aa340f4863eec03cde52a3c2911e12/data/clean/surabaya_kecamatan.geojson';
function isMyrKecamatan(name){return MYR_KECAMATAN.has(String(name||'').trim().toUpperCase());}
function kecamatanKey(name){return String(name||'').trim().toUpperCase().replace(/\s+/g,' ');}
function successColor(rate){const n=Number(rate||0);if(n<25)return '#ef4444';if(n<50)return '#f97316';if(n<75)return '#eab308';return '#22c55e';}
function successLabel(rate){const n=Number(rate||0);if(n<25)return 'RENDAH';if(n<50)return 'PERLU DITINGKATKAN';if(n<75)return 'BAIK';return 'TINGGI';}
function renderLeaderboard(rows){const el=document.querySelector('#leaderboard');if(!el)return;const data=Array.isArray(rows)?rows:[];if(!data.length){el.innerHTML='<p class="muted">BELUM ADA DATA LEADERBOARD.</p>';return;}el.innerHTML=data.slice(0,10).map((x,i)=>{const rank=i+1;return `<div class="leader-row"><span class="leader-rank">${String(rank).padStart(2,'0')}</span><div class="leader-person"><b>${esc(x.name||'-')}</b><small>${esc(x.nik||'-')} • ${esc(x.sto||'ALL')}</small></div><strong>${fmt(x.total||0)}</strong></div>`;}).join('');}
function initAreaMap(){const el=document.querySelector('#areaSuccessMap');if(!el||typeof L==='undefined')return null;if(areaMap){areaMap.invalidateSize();return areaMap;}areaMap=L.map(el,{zoomControl:true,scrollWheelZoom:true}).setView([-7.2575,112.7521],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(areaMap);areaLayer=L.layerGroup().addTo(areaMap);areaPolygonLayer=L.layerGroup().addTo(areaMap);return areaMap;}

function detailHtml(d){
  const rate=Number(d.rate||0);
  const areaRows=(Array.isArray(d.areas)?d.areas:[]).map(a=>{
    const customers=Array.isArray(a.customers)?a.customers:[];
    const customerHtml=customers.slice(0,30).map(c=>`<div class="map-customer"><b>${esc(c.customer_name||'-')}</b><small>${esc(c.service_number||'-')} • ${esc(c.status||'-')}</small><span>${esc(c.address||'-')}</span></div>`).join('');
    const more=customers.length>30?`<div class="map-more">+ ${customers.length-30} pelanggan lainnya</div>`:'';
    return `<section class="map-area-detail"><div class="map-area-head"><b>${esc(a.area||'LAINNYA')}</b><strong>${Number(a.rate||0).toLocaleString('id-ID')}%</strong></div><div class="map-area-stats"><span>${fmt(a.close)} CLOSE</span><span>${fmt(a.open)} OPEN</span><span>${fmt(a.total)} TOTAL</span></div><div class="map-customer-list">${customerHtml||'<small>Tidak ada pelanggan.</small>'}</div>${more}</section>`;
  }).join('');
  return `<div class="map-popup map-kecamatan"><b class="map-popup-title">KECAMATAN ${esc(d.kecamatan||'-')}</b><div class="map-popup-rate">${rate.toLocaleString('id-ID')}%</div><div class="map-popup-stats"><span>${fmt(d.close)} CLOSE</span><span>${fmt(d.open)} OPEN</span><span>${fmt(d.total)} TOTAL</span></div><small class="map-popup-status">${successLabel(rate)}</small><div class="map-detail-list">${areaRows||'<small>Tidak ada detail pelanggan.</small>'}</div></div>`;
}

async function openKecamatanDetail(layer,kecamatan){
  layer.bindPopup(`<div class="map-popup"><b>KECAMATAN ${esc(kecamatan)}</b><br><small>MEMUAT DETAIL PELANGGAN...</small></div>`,{maxWidth:390,minWidth:280}).openPopup();
  try{
    if(!isMyrKecamatan(kecamatan))throw new Error('Kecamatan di luar STO MYR');
    const d=await json('/api/web/area-success?kecamatan='+encodeURIComponent(kecamatan));
    if(!d?.ok)throw new Error(d?.message||'Detail gagal');
    layer.setPopupContent(detailHtml(d));
  }catch(e){layer.setPopupContent(`<div class="map-popup"><b>KECAMATAN ${esc(kecamatan)}</b><br><small>DETAIL GAGAL DIMUAT.</small></div>`);}
}

function polygonStyle(rate){const color=successColor(rate);return {weight:2,color,fillColor:color,fillOpacity:.30};}

async function renderAreaSuccessMap(data){
  const map=initAreaMap();const summary=document.querySelector('#areaMapSummary');if(!map)return;
  areaLayer.clearLayers();areaPolygonLayer.clearLayers();
  const rawAreas=Array.isArray(data?.areas)?data.areas:[];
  // Hard whitelist at UI boundary so unrelated kecamatan can never appear.
  const areas=rawAreas.filter(a=>isMyrKecamatan(a?.name||a?.kecamatan));
  const stats=new Map(areas.map(a=>[kecamatanKey(a?.name||a?.kecamatan),a]));
  let close=0,total=0;areas.forEach(a=>{close+=Number(a.close||0);total+=Number(a.total||0);});
  if(summary)summary.textContent=`${fmt(areas.length)} KECAMATAN STO MYR • ${fmt(close)} CLOSE / ${fmt(total)} TOTAL • POLYGON ADMINISTRATIF`;

  try{
    const response=await fetch(SURABAYA_KECAMATAN_GEOJSON,{cache:'force-cache'});
    if(!response.ok)throw new Error('GeoJSON HTTP '+response.status);
    const geo=await response.json();
    const features=(Array.isArray(geo?.features)?geo.features:[]).filter(f=>isMyrKecamatan(f?.properties?.kecamatan||f?.properties?.WADMKC||f?.properties?.NAMOBJ));
    if(!features.length)throw new Error('Polygon kecamatan MYR tidak ditemukan');

    const bounds=[];
    features.forEach(feature=>{
      const name=String(feature?.properties?.kecamatan||feature?.properties?.WADMKC||feature?.properties?.NAMOBJ||'').trim().toUpperCase();
      const stat=stats.get(kecamatanKey(name));
      if(!stat)return;
      const rate=Number(stat.rate||0),color=successColor(rate);
      const polygon=L.geoJSON(feature,{style:polygonStyle(rate)});
      polygon.bindTooltip(`KECAMATAN ${esc(name)} • ${Math.round(rate)}%`,{sticky:true});
      polygon.on('click',()=>openKecamatanDetail(polygon,name));
      polygon.on('mouseover',()=>polygon.setStyle({weight:3,fillOpacity:.45}));
      polygon.on('mouseout',()=>polygon.setStyle(polygonStyle(rate)));
      polygon.addTo(areaPolygonLayer);
      const center=polygon.getBounds().getCenter();
      L.marker(center,{icon:L.divIcon({className:'area-rate-marker',html:`<span style="--rate-color:${color}">${Math.round(rate)}%</span>`,iconSize:[52,28],iconAnchor:[26,14]})}).on('click',()=>openKecamatanDetail(polygon,name)).addTo(areaLayer);
      bounds.push(center);
    });
    if(bounds.length)map.fitBounds(L.latLngBounds(bounds),{padding:[20,20],maxZoom:13});
  }catch(e){
    console.warn('[AREA SUCCESS POLYGON]',e);
    if(summary)summary.textContent='POLYGON KECAMATAN GAGAL DIMUAT — CEK GEOJSON';
  }
}

async function loadAreaSuccessMap(){const summary=document.querySelector('#areaMapSummary');if(summary)summary.textContent='MEMUAT POLYGON KECAMATAN STO MYR...';try{const d=await json('/api/web/area-success');if(!d?.ok)throw new Error(d?.message||d?.error||'Area API gagal');await renderAreaSuccessMap(d);}catch(e){console.warn('[AREA SUCCESS]',e);if(summary)summary.textContent='MAP DATA GAGAL DIMUAT — CEK SESSION / API';}}

/* Popup readability patch: keep the existing visual identity, but separate
   stats and customer records so text can never run together. */
(function installAreaPopupStyles(){
  if(document.getElementById('area-popup-readable-style'))return;
  const s=document.createElement('style');s.id='area-popup-readable-style';s.textContent=`
    .map-kecamatan{min-width:280px;max-width:360px;font-size:11px;line-height:1.45}
    .map-popup-title{display:block;margin-bottom:4px;letter-spacing:.04em}
    .map-popup-rate{font-size:22px;font-weight:800;line-height:1.05;margin:2px 0 4px}
    .map-popup-stats,.map-area-stats{display:flex;flex-wrap:wrap;gap:4px 10px;color:#a8c4d1;font-size:9px;font-weight:700}
    .map-popup-status{display:block;margin:5px 0 8px;color:#55e1a1;font-weight:800}
    .map-detail-list{max-height:330px;overflow-y:auto;padding-right:4px}
    .map-area-detail{padding:8px 0;border-top:1px solid #1b3948}
    .map-area-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:3px}
    .map-area-head b{color:#66dcff;font-size:11px}
    .map-area-head strong{font-size:14px;color:#e8f7ff}
    .map-customer-list{margin-top:6px}
    .map-customer{padding:6px 0;border-top:1px solid rgba(33,69,85,.65)}
    .map-customer b,.map-customer small,.map-customer span{display:block}
    .map-customer b{font-size:10px;color:#e6f5fa}
    .map-customer small{font-size:8px;color:#62dfff;margin-top:2px}
    .map-customer span{font-size:8px;line-height:1.35;color:#7895a4;margin-top:2px;white-space:normal}
    .map-more{padding-top:6px;color:#55e1a1;font-size:8px;font-weight:800}
    .leaflet-popup-content{margin:10px 12px}
  `;document.head.appendChild(s);
})();

/* FULL MAP workspace: map on the left, selected kecamatan/customer detail on the right. */
let fullMap=null,fullPolygonLayer=null,fullMarkerLayer=null;
const fullMapGeoCache={features:null};
function fullMapDetailEmpty(){return '<div class="full-map-placeholder">KLIK SALAH SATU AREA DI PETA<br><small>DETAIL PELANGGAN AKAN MUNCUL DI SINI</small></div>';}
function ensureFullMapWorkspace(){
  let ws=document.getElementById('fullMapWorkspace');
  if(ws)return ws;
  ws=document.createElement('section');ws.id='fullMapWorkspace';ws.className='full-map-workspace';
  ws.innerHTML='<div class="full-map-canvas"><div class="full-map-head"><div class="full-map-title">AREA SUCCESS / FULL MAP</div><button id="fullMapClose" type="button" class="full-map-close">✕ TUTUP</button></div><div id="fullMapLeaflet" class="full-map-leaflet"></div></div><aside class="full-map-detail"><div class="full-map-detail-head"><small>AREA INTELLIGENCE</small><h3 id="fullMapDetailTitle">PILIH AREA</h3></div><div id="fullMapDetailBody" class="full-map-detail-body">'+fullMapDetailEmpty()+'</div><div id="fullMapStatus" class="full-map-status">PILIH KECAMATAN STO MYR</div></aside></section>';
  document.body.appendChild(ws);
  document.getElementById('fullMapClose').addEventListener('click',closeFullMap);
  return ws;
}
async function getFullMapFeatures(){
  if(fullMapGeoCache.features)return fullMapGeoCache.features;
  const response=await fetch(SURABAYA_KECAMATAN_GEOJSON,{cache:'force-cache'});if(!response.ok)throw new Error('GeoJSON HTTP '+response.status);
  const geo=await response.json();
  fullMapGeoCache.features=(Array.isArray(geo?.features)?geo.features:[]).filter(f=>isMyrKecamatan(f?.properties?.kecamatan||f?.properties?.WADMKC||f?.properties?.NAMOBJ));
  return fullMapGeoCache.features;
}
function setFullMapDetailLoading(name){const t=document.getElementById('fullMapDetailTitle'),b=document.getElementById('fullMapDetailBody'),s=document.getElementById('fullMapStatus');if(t)t.textContent='KECAMATAN '+name;if(b)b.innerHTML='<div class="full-map-placeholder">MEMUAT DETAIL PELANGGAN...</div>';if(s)s.textContent='MEMUAT DATA '+name+'...';}
function setFullMapDetail(d){const t=document.getElementById('fullMapDetailTitle'),b=document.getElementById('fullMapDetailBody'),s=document.getElementById('fullMapStatus');if(t)t.textContent='KECAMATAN '+String(d?.kecamatan||'-');if(b)b.innerHTML=detailHtml(d);if(s)s.textContent=`${fmt(d?.close||0)} CLOSE • ${fmt(d?.open||0)} OPEN • ${fmt(d?.total||0)} TOTAL • ${successLabel(d?.rate||0)}`;}
async function selectFullMapArea(name){
  if(!isMyrKecamatan(name))return;setFullMapDetailLoading(name);
  try{const d=await json('/api/web/area-success?kecamatan='+encodeURIComponent(name));if(!d?.ok)throw new Error(d?.message||'Detail gagal');setFullMapDetail(d);}catch(e){const b=document.getElementById('fullMapDetailBody'),s=document.getElementById('fullMapStatus');if(b)b.innerHTML='<div class="full-map-placeholder">DETAIL GAGAL DIMUAT<br><small>CEK SESSION / API</small></div>';if(s)s.textContent='GAGAL MEMUAT DETAIL';}
}
async function renderFullMap(){
  const d=await json('/api/web/area-success');if(!d?.ok)throw new Error(d?.message||d?.error||'Area API gagal');
  const stats=new Map((Array.isArray(d.areas)?d.areas:[]).filter(a=>isMyrKecamatan(a?.name||a?.kecamatan)).map(a=>[kecamatanKey(a?.name||a?.kecamatan),a]));
  const features=await getFullMapFeatures();fullPolygonLayer.clearLayers();fullMarkerLayer.clearLayers();const bounds=[];
  features.forEach(feature=>{const name=String(feature?.properties?.kecamatan||feature?.properties?.WADMKC||feature?.properties?.NAMOBJ||'').trim().toUpperCase();const stat=stats.get(kecamatanKey(name));if(!stat)return;const rate=Number(stat.rate||0),color=successColor(rate);const polygon=L.geoJSON(feature,{style:polygonStyle(rate)});polygon.bindTooltip('KECAMATAN '+esc(name)+' • '+Math.round(rate)+'%',{sticky:true});polygon.on('click',()=>selectFullMapArea(name));polygon.on('mouseover',()=>polygon.setStyle({weight:3,fillOpacity:.45}));polygon.on('mouseout',()=>polygon.setStyle(polygonStyle(rate)));polygon.addTo(fullPolygonLayer);const center=polygon.getBounds().getCenter();L.marker(center,{icon:L.divIcon({className:'area-rate-marker',html:`<span style="--rate-color:${color}">${Math.round(rate)}%</span>`,iconSize:[52,28],iconAnchor:[26,14]}),keyboard:true}).on('click',()=>selectFullMapArea(name)).addTo(fullMarkerLayer);bounds.push(center);});
  if(bounds.length)fullMap.fitBounds(L.latLngBounds(bounds),{padding:[35,35],maxZoom:13});
}
async function openFullMap(){
  const ws=ensureFullMapWorkspace();ws.classList.add('is-open');document.body.style.overflow='hidden';
  if(!fullMap){const el=document.getElementById('fullMapLeaflet');fullMap=L.map(el,{zoomControl:true,scrollWheelZoom:true}).setView([-7.2575,112.7521],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(fullMap);fullPolygonLayer=L.layerGroup().addTo(fullMap);fullMarkerLayer=L.layerGroup().addTo(fullMap);}
  setTimeout(()=>fullMap.invalidateSize(),60);try{await renderFullMap();}catch(e){console.warn('[FULL MAP]',e);const s=document.getElementById('fullMapStatus');if(s)s.textContent='MAP GAGAL DIMUAT — CEK SESSION / API';}
}
function closeFullMap(){const ws=document.getElementById('fullMapWorkspace');if(ws)ws.classList.remove('is-open');document.body.style.overflow='';}
(function installFullMapButton(){
  const btn=document.getElementById('fullMapBtn');if(!btn)return;btn.addEventListener('click',openFullMap);
})();
