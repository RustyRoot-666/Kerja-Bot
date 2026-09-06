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

/* Dashboard polish: keep leaderboard filters compact and aligned on narrow panels. */
(function installDashboardPolish(){
  const styleId='dashboard-polish-style';
  if(document.getElementById(styleId)) return;
  const s=document.createElement('style');
  s.id=styleId;
  s.textContent=`
    .status-panel .panel-head{margin-bottom:10px;align-items:center}
    .status-panel .leader-filterbar{
      display:grid;
      grid-template-columns:42px repeat(3,minmax(0,1fr));
      gap:5px;
      align-items:center;
      margin:0 0 10px;
      padding:0;
    }
    .status-panel .leader-filterbar .filter-label{
      margin:0!important;
      font-size:7px;
      line-height:1;
      text-align:left;
      white-space:nowrap;
    }
    .status-panel .leader-filterbar .filter-btn{
      width:100%;
      min-width:0;
      padding:7px 5px;
      font-size:7px;
      line-height:1;
      text-align:center;
      white-space:nowrap;
    }
    .status-panel .leaderboard-note{
      margin-top:7px;
      padding-top:7px;
      border-top:1px solid #122d3a;
    }
    .status-panel .leaderboard{gap:5px}
    .status-panel .leader-row{grid-template-columns:28px minmax(0,1fr) auto;padding:10px 9px}
    @media(max-width:650px){
      .status-panel .leader-filterbar{grid-template-columns:38px repeat(3,minmax(0,1fr));gap:4px}
      .status-panel .leader-filterbar .filter-btn{padding:7px 3px;font-size:6.5px}
    }
  `;
  document.head.appendChild(s);
})();
