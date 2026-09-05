(function(){
  'use strict';
  const tg=window.Telegram?.WebApp;
  if(!tg || !tg.initData || !navigator.geolocation) return;
  tg.ready();
  let timer=null, started=false;
  async function send(pos){
    const body={init_data:tg.initData,latitude:pos.coords.latitude,longitude:pos.coords.longitude,accuracy:pos.coords.accuracy};
    try{await fetch('/api/technician-location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',keepalive:true});}catch(e){console.debug('location heartbeat failed',e);}
  }
  function locate(){navigator.geolocation.getCurrentPosition(send,()=>{}, {enableHighAccuracy:true,maximumAge:30000,timeout:15000});}
  function start(){if(started)return;started=true;locate();timer=setInterval(locate,60000);}
  function stop(){if(timer)clearInterval(timer);timer=null;started=false;}
  function request(){
    if(!window.__KERJA_LOCATION_REQUESTED){
      window.__KERJA_LOCATION_REQUESTED=true;
      navigator.geolocation.getCurrentPosition(send,()=>{window.__KERJA_LOCATION_PERMISSION_DENIED=true;}, {enableHighAccuracy:true,maximumAge:0,timeout:15000});
    }
    start();
  }
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')request();else stop();});
  window.KerjaBotLocation={request,start,stop};
  setTimeout(request,1200);
})();
