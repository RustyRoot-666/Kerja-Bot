(function(){
  'use strict';

  const tg=window.Telegram?.WebApp;
  if(!tg || !tg.initData || !navigator.geolocation) return;
  tg.ready();

  let timer=null, started=false, permissionState='unknown';
  const KEY='kerja-bot-location-permission-v2';
  const LEGACY_KEY='kerja-bot-location-permission-v1';

  function saveState(value){
    permissionState=value;
    try{localStorage.setItem(KEY,value)}catch(e){}
  }

  function loadState(){
    try{
      return localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'unknown';
    }catch(e){return 'unknown'}
  }

  async function send(pos){
    const body={init_data:tg.initData,latitude:pos.coords.latitude,longitude:pos.coords.longitude,accuracy:pos.coords.accuracy};
    try{await fetch('/api/technician-location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',keepalive:true});}
    catch(e){console.debug('location heartbeat failed',e);}
  }

  function locate(){
    navigator.geolocation.getCurrentPosition(
      pos=>{saveState('granted');send(pos)},
      err=>{
        if(err?.code===1) saveState('denied');
        else if(err?.code===2) saveState('unavailable');
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

  async function browserPermission(){
    if(!navigator.permissions?.query) return null;
    try{
      const result=await navigator.permissions.query({name:'geolocation'});
      permissionState=result.state;
      try{localStorage.setItem(KEY,result.state)}catch(e){}
      result.onchange=()=>{
        permissionState=result.state;
        try{localStorage.setItem(KEY,result.state)}catch(e){}
        if(result.state==='granted' && document.visibilityState==='visible') start();
      };
      return result.state;
    }catch(e){return null}
  }

  async function silentStart(){
    const state=await browserPermission();

    // Never trigger a permission prompt automatically when the Mini App opens.
    // If permission is still "prompt", wait for an explicit user action.
    if(state==='granted'){
      start();
      return;
    }
    if(state==='denied'){
      saveState('denied');
      return;
    }
    if(state==='prompt'){
      permissionState='prompt';
      return;
    }

    // Older Telegram WebViews may not expose Permissions API. Resume silently
    // only when a previous session already recorded that permission was granted.
    if(loadState()==='granted') start();
  }

  async function request(){
    // This is the only path allowed to trigger the native permission dialog.
    // It should be called from an explicit user gesture.
    const state=await browserPermission();
    if(state==='granted'){
      saveState('granted');
      start();
      return;
    }
    if(state==='denied'){
      saveState('denied');
      start();
      return;
    }

    navigator.geolocation.getCurrentPosition(
      pos=>{saveState('granted');send(pos);start()},
      err=>{
        if(err?.code===1) saveState('denied');
        else if(err?.code===2) saveState('unavailable');
        else saveState('unavailable');
        start();
      },
      {enableHighAccuracy:true,maximumAge:0,timeout:15000}
    );
  }

  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible') silentStart();
    else stop();
  });

  window.KerjaBotLocation={request,start,stop,permission:browserPermission};

  // Intentionally silent. Opening/reopening the Mini App must not request
  // location permission repeatedly.
  setTimeout(silentStart,1200);
})();
