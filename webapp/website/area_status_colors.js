/* Area Success status emphasis.
   CLOSE orders are highlighted green; OPEN stays neutral for quick scanning. */
(function installAreaStatusColors(){
  const styleId='area-status-colors-style';
  if(!document.getElementById(styleId)){
    const s=document.createElement('style');
    s.id=styleId;
    s.textContent=`
      .map-customer small.area-status-close{color:#39e1a0!important;font-weight:800!important}
      .map-customer small.area-status-open{color:#ffb454!important;font-weight:800!important}
      .map-customer small.area-status-other{color:#62dfff!important;font-weight:800!important}
    `;
    document.head.appendChild(s);
  }
  function apply(){
    document.querySelectorAll('.map-customer small').forEach(el=>{
      const text=String(el.textContent||'').toUpperCase();
      el.classList.remove('area-status-close','area-status-open','area-status-other');
      if(/•\s*CLOSE\b/.test(text)) el.classList.add('area-status-close');
      else if(/•\s*OPEN\b/.test(text)) el.classList.add('area-status-open');
      else el.classList.add('area-status-other');
    });
  }
  apply();
  new MutationObserver(apply).observe(document.body,{subtree:true,childList:true});
})();
