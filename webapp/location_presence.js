(function(){
  'use strict';
  const tg=window.Telegram?.WebApp;
  if(!tg || !tg.initData || !navigator.geolocation) return;
  tg.ready();

  let timer=null, started=false, permissionState='unknown';
  const KEY='kerja-bot-location-permission-v1';

  function saveState(value){
    permissionState=value;
    try{localStorage.setItem(KEY,value)}catch(e){}
  }
  function loadState(){
    try{return localStorage.getItem(KEY)||'unknown'}catch(e){return 'unknown'}
  }

  async function send(pos){
    const body={init_data:tg.initData,latitude:pos.coords.latitude,longitude:pos.coords.longitude,accuracy:pos.coords.accuracy};
    try{await fetch('/api/technician-location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',keepalive:true});}catch(e){console.debug('location heartbeat failed',e);}
  }

  function locate(){
    navigator.geolocation.getCurrentPosition(
      pos=>{saveState('granted');send(pos)},
      err=>{
        if(err?.code===1) saveState('denied');
        else if(permissionState==='unknown') saveState('unavailable');
      },
      {enableHighAccuracy:true,maximumAge:30000,timeout:15000}
    );
  }

  function start(){
    if(started)return;
    started=true;
    locate();
    timer=setInterval(locate,60000);
  }

  function stop(){
    if(timer)clearInterval(timer);
    timer=null;
    started=false;
  }

  function request(){
    permissionState=loadState();
    // Do not deliberately request permission on every Mini App open.
    // Once the browser/Telegram WebView has granted access, simply use it.
    if(permissionState==='granted' || permissionState==='denied' || permissionState==='unavailable'){
      start();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      pos=>{saveState('granted');send(pos);start()},
      err=>{
        if(err?.code===1) saveState('denied');
        else saveState('unavailable');
        start();
      },
      {enableHighAccuracy:true,maximumAge:0,timeout:15000}
    );
  }

  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible'){
      // If permission is already known, resume silently.
      if(loadState()==='granted') start();
    }else stop();
  });

  window.KerjaBotLocation={request,start,stop};
  setTimeout(request,1200);
})();
