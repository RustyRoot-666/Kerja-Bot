let areaMap=null;
let areaLayer=null;

// STO MYR service territory confirmed from the MYR replacement-order dataset.
// The public Area Success Map must show ONLY these kecamatan.
const MYR_KECAMATAN = new Set(['SUKOLILO','MULYOREJO','GUBENG','TAMBAKSARI','TENGGILIS MEJOYO','RUNGKUT']);
function isMyrKecamatan(name){return MYR_KECAMATAN.has(String(name||'').trim().toUpperCase());}

function successColor(rate){const n=Number(rate||0);if(n<25)return '#ef4444';if(n<50)return '#f97316';if(n<75)return '#eab308';return '#22c55e';}
function successLabel(rate){const n=Number(rate||0);if(n<25)return 'RENDAH';if(n<50)return 'PERLU DITINGKATKAN';if(n<75)return 'BAIK';return 'TINGGI';}
function renderLeaderboard(rows){const el=document.querySelector('#leaderboard');if(!el)return;const data=Array.isArray(rows)?rows:[];if(!data.length){el.innerHTML='<p class="muted">BELUM ADA DATA LEADERBOARD.</p>';return;}el.innerHTML=data.slice(0,10).map((x,i)=>{const rank=i+1;return `<div class="leader-row"><span class="leader-rank">${String(rank).padStart(2,'0')}</span><div class="leader-person"><b>${esc(x.name||'-')}</b><small>${esc(x.nik||'-')} • ${esc(x.sto||'ALL')}</small></div><strong>${fmt(x.total||0)}</strong></div>`;}).join('');}
function initAreaMap(){const el=document.querySelector('#areaSuccessMap');if(!el||typeof L==='undefined')return null;if(areaMap){areaMap.invalidateSize();return areaMap;}areaMap=L.map(el,{zoomControl:true,scrollWheelZoom:true}).setView([-7.2575,112.7521],12);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(areaMap);areaLayer=L.layerGroup().addTo(areaMap);return areaMap;}

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

async function openKecamatanDetail(circle,kecamatan){
  circle.bindPopup(`<div class="map-popup"><b>KECAMATAN ${esc(kecamatan)}</b><br><small>MEMUAT DETAIL PELANGGAN...</small></div>`).openPopup();
  try{
    if(!isMyrKecamatan(kecamatan))throw new Error('Kecamatan di luar STO MYR');
    const d=await json('/api/web/area-success?kecamatan='+encodeURIComponent(kecamatan));
    if(!d?.ok)throw new Error(d?.message||'Detail gagal');
    circle.setPopupContent(detailHtml(d));
  }catch(e){circle.setPopupContent(`<div class="map-popup"><b>KECAMATAN ${esc(kecamatan)}</b><br><small>DETAIL GAGAL DIMUAT.</small></div>`);}
}

function renderAreaSuccessMap(data){
  const map=initAreaMap();const summary=document.querySelector('#areaMapSummary');if(!map)return;areaLayer.clearLayers();
  const rawAreas=Array.isArray(data?.areas)?data.areas:[];
  // Hard whitelist at UI boundary so unrelated kecamatan (e.g. WIYUNG,
  // WONOKROMO, KARANG PILANG, etc.) can never appear on the MYR map.
  const areas=rawAreas.filter(a=>isMyrKecamatan(a?.name||a?.kecamatan));
  const bounds=[];let close=0,total=0,geocoded=0;
  areas.forEach(a=>{close+=Number(a.close||0);total+=Number(a.total||0);if(a.geocoded)geocoded++;});
  if(summary)summary.textContent=`${fmt(areas.length)} KECAMATAN STO MYR • ${fmt(close)} CLOSE / ${fmt(total)} TOTAL • ${fmt(geocoded)} MAP POINT`;
  areas.forEach(a=>{
    if(!a.geocoded||a.latitude==null||a.longitude==null)return;
    const rate=Number(a.rate||0),color=successColor(rate),radius=Number(a.radius_m||1200);
    const kec=String(a.name||a.range||a.kecamatan||'-').trim().toUpperCase();
    if(!isMyrKecamatan(kec))return;
    const circle=L.circle([Number(a.latitude),Number(a.longitude)],{radius,weight:2,color,fillColor:color,fillOpacity:.22});
    circle.on('click',()=>openKecamatanDetail(circle,kec));
    circle.bindTooltip(`KECAMATAN ${esc(kec)}`,{direction:'top',offset:[0,-10]});
    circle.addTo(areaLayer);
    L.marker([Number(a.latitude),Number(a.longitude)],{icon:L.divIcon({className:'area-rate-marker',html:`<span style="--rate-color:${color}">${Math.round(rate)}%</span>`,iconSize:[52,28],iconAnchor:[26,14]})}).on('click',()=>openKecamatanDetail(circle,kec)).addTo(areaLayer);
    bounds.push([Number(a.latitude),Number(a.longitude)]);
  });
  if(bounds.length)map.fitBounds(bounds,{padding:[20,20],maxZoom:13});
}
async function loadAreaSuccessMap(){const summary=document.querySelector('#areaMapSummary');if(summary)summary.textContent='MEMUAT KECAMATAN STO MYR...';try{const d=await json('/api/web/area-success');if(!d?.ok)throw new Error(d?.message||d?.error||'Area API gagal');renderAreaSuccessMap(d);}catch(e){console.warn('[AREA SUCCESS]',e);if(summary)summary.textContent='MAP DATA GAGAL DIMUAT — CEK SESSION / API';}}
