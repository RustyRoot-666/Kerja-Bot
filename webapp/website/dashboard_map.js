let areaMap=null;
let areaLayer=null;

function successColor(rate){
  const n=Number(rate||0);
  if(n<25)return '#ef4444';
  if(n<50)return '#f97316';
  if(n<75)return '#eab308';
  return '#22c55e';
}
function successLabel(rate){
  const n=Number(rate||0);
  if(n<25)return 'RENDAH';
  if(n<50)return 'PERLU DITINGKATKAN';
  if(n<75)return 'BAIK';
  return 'TINGGI';
}
function renderLeaderboard(rows){
  const el=document.querySelector('#leaderboard');
  if(!el)return;
  const data=Array.isArray(rows)?rows:[];
  if(!data.length){el.innerHTML='<p class="muted">BELUM ADA DATA LEADERBOARD.</p>';return;}
  el.innerHTML=data.slice(0,10).map((x,i)=>{
    const rank=i+1;
    const name=esc(x.name||'-');
    const nik=esc(x.nik||'-');
    const total=fmt(x.total||0);
    return `<div class="leader-row"><span class="leader-rank">${String(rank).padStart(2,'0')}</span><div class="leader-person"><b>${name}</b><small>${nik} • ${esc(x.sto||'ALL')}</small></div><strong>${total}</strong></div>`;
  }).join('');
}
function initAreaMap(){
  const el=document.querySelector('#areaSuccessMap');
  if(!el||typeof L==='undefined')return null;
  if(areaMap){areaMap.invalidateSize();return areaMap;}
  areaMap=L.map(el,{zoomControl:true,scrollWheelZoom:true}).setView([-7.2575,112.7521],12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(areaMap);
  areaLayer=L.layerGroup().addTo(areaMap);
  return areaMap;
}
function renderAreaSuccessMap(data){
  const map=initAreaMap();
  const summary=document.querySelector('#areaMapSummary');
  if(!map)return;
  areaLayer.clearLayers();
  const areas=Array.isArray(data?.areas)?data.areas:[];
  const bounds=[];
  let close=0,total=0;
  areas.forEach(a=>{close+=Number(a.close||0);total+=Number(a.total||0)});
  if(summary)summary.textContent=`${fmt(areas.length)} RANGE • ${fmt(close)} CLOSE / ${fmt(total)} TOTAL`;
  areas.forEach(a=>{
    if(!a.geocoded||a.latitude==null||a.longitude==null)return;
    const rate=Number(a.rate||0),color=successColor(rate),radius=Number(a.radius_m||180);
    const circle=L.circle([Number(a.latitude),Number(a.longitude)],{radius,weight:2,color,fillColor:color,fillOpacity:.28});
    circle.bindPopup(`<div class="map-popup"><b>${esc(a.range)}</b><br><strong>${rate.toLocaleString('id-ID')}%</strong> keberhasilan<br><span>${fmt(a.close)} CLOSE • ${fmt(a.open)} OPEN</span><br><small>${successLabel(rate)}</small></div>`);
    circle.addTo(areaLayer);
    L.marker([Number(a.latitude),Number(a.longitude)],{icon:L.divIcon({className:'area-rate-marker',html:`<span style="--rate-color:${color}">${Math.round(rate)}%</span>`,iconSize:[52,28],iconAnchor:[26,14]})}).bindTooltip(esc(a.range),{direction:'top',offset:[0,-10]}).addTo(areaLayer);
    bounds.push([Number(a.latitude),Number(a.longitude)]);
  });
  if(bounds.length)map.fitBounds(bounds,{padding:[20,20],maxZoom:14});
}
async function loadAreaSuccessMap(){
  try{const d=await json('/api/web/area-success');renderAreaSuccessMap(d);}catch(e){const s=document.querySelector('#areaMapSummary');if(s)s.textContent='MAP DATA GAGAL DIMUAT';}
}
