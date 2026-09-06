(function(){
  'use strict';

  const tg=window.Telegram?.WebApp;
  if(!tg || !tg.initData) return;
  tg.ready();

  const hasGeo=!!navigator.geolocation;
  let timer=null, presenceTimer=null, started=false, presenceStarted=false, permissionState='unknown';
  const KEY='kerja-bot-location-permission-v2';
  const LEGACY_KEY='kerja-bot-location-permission-v1';
  const PRESENCE_INTERVAL=30000;

  function saveState(value){
    permissionState=value;
    try{localStorage.setItem(KEY,value)}catch(e){}
  }

  function loadState(){
    try{
      return localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'unknown';
    }catch(e){return 'unknown'}
  }

  async function sendPresence(){
    try{
      await fetch('/api/technician-presence',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({init_data:tg.initData}),
        cache:'no-store',
        keepalive:true
      });
    }catch(e){console.debug('presence heartbeat failed',e);}
  }

  function startPresence(){
    if(presenceStarted)return;
    presenceStarted=true;
    sendPresence();
    presenceTimer=setInterval(sendPresence,PRESENCE_INTERVAL);
  }

  function stopPresence(){
    if(presenceTimer)clearInterval(presenceTimer);
    presenceTimer=null;
    presenceStarted=false;
  }

  async function send(pos){
    const body={init_data:tg.initData,latitude:pos.coords.latitude,longitude:pos.coords.longitude,accuracy:pos.coords.accuracy};
    try{await fetch('/api/technician-location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',keepalive:true});}
    catch(e){console.debug('location heartbeat failed',e);}
  }

  function locate(){
    if(!hasGeo)return;
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
    if(started || !hasGeo)return;
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
    if(!hasGeo || !navigator.permissions?.query)return null;
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
    startPresence();
    const state=await browserPermission();

    // Never trigger a permission prompt automatically when the Mini App opens.
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
    if(!hasGeo)return;
    startPresence();
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
    else {stop();stopPresence();}
  });

  window.KerjaBotLocation={request,start,stop,permission:browserPermission};

  // Opening/reopening the Mini App marks the technician ONLINE without
  // requesting GPS permission. GPS resumes silently only when already granted.
  setTimeout(silentStart,1200);
})();
