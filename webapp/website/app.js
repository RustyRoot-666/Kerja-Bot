const $=s=>document.querySelector(s);
const authCard=$('#authCard'),dashboard=$('#dashboard'),linkView=$('#linkView'),loginView=$('#loginView');
function msg(el,text){el.textContent=text||''}
function showLogin(){linkView.classList.add('hidden');loginView.classList.remove('hidden')}
function showLink(){loginView.classList.add('hidden');linkView.classList.remove('hidden')}
async function json(url,options={}){const r=await fetch(url,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let d={};try{d=await r.json()}catch{} if(!r.ok)throw Object.assign(new Error(d.message||d.error||'Request gagal'),{data:d,status:r.status});return d}

async function requestLink(){
 const id=$('#telegramId').value.trim();
 if(!/^\d{5,20}$/.test(id)){msg($('#linkStatus'),'Masukkan Telegram ID yang valid.');return}
 $('#linkBtn').disabled=true;msg($('#linkStatus'),'Mengirim permintaan ke Telegram...');
 try{const d=await json('/api/auth/link/request',{method:'POST',body:JSON.stringify({telegram_id:id})});
   msg($('#linkStatus'),'Permintaan terkirim. Buka Telegram dan tekan tombol konfirmasi dari Kerja-Bot.');
   pollLink(d.token);
 }catch(e){msg($('#linkStatus'),e.message)}finally{$('#linkBtn').disabled=false}
}
async function pollLink(token){
 let tries=0; const timer=setInterval(async()=>{tries++;try{const d=await json('/api/auth/link/status?token='+encodeURIComponent(token));
   if(d.status==='confirmed'){clearInterval(timer);if(d.has_web_account){msg($('#linkStatus'),'Telegram terverifikasi. Silakan masuk menggunakan NIK dan password dari chatbot.');showLogin();$('#nik').value=d.technician?.nik||'';}else{msg($('#linkStatus'),'Telegram terverifikasi, tetapi akun Website belum dibuat oleh admin. Minta admin menjalankan /webaccount di chatbot.');}}
   else if(d.status==='expired'){clearInterval(timer);msg($('#linkStatus'),'Permintaan kedaluwarsa. Silakan ulangi.');}
 }catch(e){clearInterval(timer);msg($('#linkStatus'),e.message)} if(tries>=60)clearInterval(timer)},3000)}

async function login(){
 const nik=$('#nik').value.trim(),password=$('#password').value;
 if(!nik||!password){msg($('#loginStatus'),'NIK dan password wajib diisi.');return}
 $('#loginBtn').disabled=true;msg($('#loginStatus'),'Memeriksa akun...');
 try{await json('/api/auth/login',{method:'POST',body:JSON.stringify({nik,password})});await loadDashboard();}
 catch(e){msg($('#loginStatus'),e.message)}finally{$('#loginBtn').disabled=false}
}
async function loadDashboard(){
 try{const me=await json('/api/auth/me');authCard.classList.add('hidden');dashboard.classList.remove('hidden');
   $('#welcome').textContent='Halo, '+me.technician.name;
   $('#identity').textContent=`NIK ${me.technician.nik} • STO ${me.technician.sto||'-'}`;
   $('#role').textContent=String(me.technician.role||'technician').toUpperCase();
   const r=await json('/api/web/my-report');
   $('#daily').textContent=r.daily??0;$('#weekly').textContent=r.weekly??0;$('#total').textContent=r.all??0;
   const o=await json('/api/web/open-orders');
   const items=[];(o.areas||[]).forEach(a=>(a.orders||[]).forEach(x=>items.push(x)));
   $('#orderCount').textContent=items.length+' open';
   $('#orders').innerHTML=items.length?items.slice(0,20).map(x=>`<article class="order"><b>${esc(x.customer_name)}</b><small>${esc(x.service_number)} • ${esc(x.ticket_id)}<br>${esc(x.address)}</small><span class="tag">OPEN</span></article>`).join(''):'<p class="muted">Tidak ada order open.</p>';
 }catch(e){authCard.classList.remove('hidden');dashboard.classList.add('hidden');showLogin();msg($('#loginStatus'),e.message)}
}
function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
async function logout(){await json('/api/auth/logout',{method:'POST',body:'{}'}).catch(()=>{});location.reload()}
$('#linkBtn').onclick=requestLink;$('#showLogin').onclick=showLogin;$('#showLink').onclick=showLink;$('#loginBtn').onclick=login;$('#logoutBtn').onclick=logout;
loadDashboard();
