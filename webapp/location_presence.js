(function(){
  'use strict';

  const tg=window.Telegram?.WebApp;
  if(!tg || !tg.initData || !navigator.geolocation) return;
  tg.ready();

  let timer=null, started=false, permissionState='unknown';
  const KEY='kerja-bot-location-permission-v2';

  function saveState(value){
    permissionState=value;
    try{localStorage.setItem(KEY,value)}catch(e){}
  }

  function loadState(){
    try{return localStorage.getItem(KEY)||'unknown'}catch(e){return 'unknown'}
  }

  async function send(pos){
    const body={
      init_data:tg.initData,
      latitude:pos.coords.latitude,
      longitude:pos.coords.longitude,
      accuracy:pos.coords.accuracy
    };
    try{
      await fetch('/api/technician-location',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),
        cache:'no-store',
        keepalive:true
      });
    }catch(e){console.debug('location heartbeat failed',e);}
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

    // IMPORTANT: never trigger a permission prompt automatically when the
    // Mini App opens. If the browser reports "prompt", wait for an explicit
    // user action through KerjaBotLocation.request().
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

    // Older Telegram WebViews may not expose Permissions API. Only resume
    // silently when we previously know that permission was granted.
    if(loadState()==='granted') start();
  }

  async function request(){
    // This function is intentionally the ONLY path that may open the native
    // location permission dialog. Call it from an explicit user gesture.
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
    if(document.visibilityState==='visible'){
      // Resume only when permission is already granted. Never prompt merely
      // because the user returned to the Mini App.
      silentStart();
    }else{
      stop();
    }
  });

  window.KerjaBotLocation={request,start,stop,permission:browserPermission};

  // Do NOT call request() here. Opening the Mini App must not show the
  // native permission dialog repeatedly.
  setTimeout(silentStart,1200);
})();
