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
    const more=customers.length>30?`<small>+ ${customers.length-30} pelanggan lainnya</small>`:'';
    return `<div class="map-area-detail"><b>${esc(a.area||'LAINNYA')}</b><strong>${Number(a.rate||0).toLocaleString('id-ID')}%</strong><span>${fmt(a.close)} CLOSE • ${fmt(a.open)} OPEN • ${fmt(a.total)} TOTAL</span>${customerHtml}${more}</div>`;
  }).join('');
  return `<div class="map-popup map-kecamatan"><b>KECAMATAN ${esc(d.kecamatan||'-')}</b><div class="map-popup-rate">${rate.toLocaleString('id-ID')}%</div><span>${fmt(d.close)} CLOSE • ${fmt(d.open)} OPEN • ${fmt(d.total)} TOTAL</span><small>${successLabel(rate)}</small><div class="map-detail-list">${areaRows||'<small>Tidak ada detail pelanggan.</small>'}</div></div>`;
}

async function openKecamatanDetail(layer,kecamatan){
  layer.bindPopup(`<div class="map-popup"><b>KECAMATAN ${esc(kecamatan)}</b><br><small>MEMUAT DETAIL PELANGGAN...</small></div>`).openPopup();
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
