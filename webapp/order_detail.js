// Clickable Orderanku cards with detail + WhatsApp helper.
// Orderanku merges MYR Sheet orders and JGR Work Order JAGIR while preserving ownership.

const orderankuFilter = { sto: 'ALL', jagirArea: 'ALL' };
const orderankuWhatsappStatus = new Map();

function orderankuWaStatusKey(order) {
  return orderankuWaPhone(order?.customer_phone);
}

function orderankuWaStatusHtml(order) {
  const key = orderankuWaStatusKey(order);
  const status = orderankuWhatsappStatus.get(key);
  if (status?.exists === true) return '🟢 WA VALID — TERDAFTAR';
  if (status?.exists === false) return '🔴 WA TIDAK TERDAFTAR';
  return '⚪ WA: BELUM DICEK';
}

function setOrderankuWaStatus(order, exists, checkedAt = '') {
  const key = orderankuWaStatusKey(order);
  if (!key) return;
  orderankuWhatsappStatus.set(key, {
    exists: exists === true ? true : exists === false ? false : null,
    checkedAt: checkedAt || ''
  });
}

async function restoreOrderankuWhatsappStatus(order, target) {
  const phone = orderankuWaPhone(order?.customer_phone);
  const user = typeof telegramUser === 'function' ? telegramUser() : (window.Telegram?.WebApp?.initDataUnsafe?.user || null);
  if (!phone || !user?.id || !target) return;
  try {
    const qs = new URLSearchParams({ telegram_id: String(user.id), phone, cached_only: '1' });
    const r = await fetch('/api/whatsapp-check?' + qs.toString(), { cache: 'no-store' });
    const d = await r.json();
    if (!r.ok || !d.ok) return;
    if (d.exists_whatsapp === true || d.exists_whatsapp === false) {
      setOrderankuWaStatus(order, d.exists_whatsapp, d.checked_at);
      target.textContent = orderankuWaStatusHtml(order);
    }
  } catch (_) {
    // Keep the explicit "belum dicek" state when no cached result is available.
  }
}

function orderankuWaText(order) {
  if (typeof whatsappCustomerText === 'function') return whatsappCustomerText(order);
  const technician = String(state.myOpenOrders?.technician?.name || telegramName() || 'Teknisi').trim();
  const customer = String(order.customer_name || 'Bapak/Ibu').trim();
  const inet = String(order.service_number || '-').trim();
  const address = String(order.address || '-').trim();
  const phone = String(order.customer_phone || '-').trim();
  const hour = new Date().getHours();
  const greeting = hour < 11 ? 'Selamat pagi' : hour < 15 ? 'Selamat siang' : hour < 18 ? 'Selamat sore' : 'Selamat malam';
  return `${greeting} Bapak/Ibu ${customer}.\n\nPerkenalkan, saya ${technician}, teknisi resmi IndiHome.\n\nMohon maaf mengganggu waktunya. Saya mendapat penugasan dari pihak Telkom untuk melakukan penggantian ONT/Modem pada layanan Bapak/Ibu sebagai bagian dari pembaruan perangkat jaringan.\n\nNo. Internet: ${inet}\nAlamat: ${address}\nNo. HP: ${phone}\n\nDengan penggantian perangkat ini, Bapak/Ibu akan mendapatkan beberapa benefit:\n• Jaringan lebih stabil\n• Perangkat kompatibel dengan jaringan WiFi 5 GHz\n• Biaya langganan tetap, tidak berubah\n• Tidak ada biaya pemasangan / GRATIS\n\nPekerjaan penggantian perangkat akan dilakukan oleh teknisi resmi IndiHome/Telkom yang mendapat penugasan.\n\nApabila Bapak/Ibu berkenan, mohon konfirmasi waktu yang sesuai agar saya dapat melakukan kunjungan.\n\nJika terdapat kendala atau membutuhkan konfirmasi terkait layanan, Bapak/Ibu dapat menghubungi layanan resmi Telkom melalui 188.\n\nTerima kasih atas perhatian dan kerja sama Bapak/Ibu. 🙏🏼`;
}

function orderankuWaPhone(phone) {
  let p = String(phone || '').trim().replace(/[^0-9]/g, '');
  if (!p) return '';
  if (p.startsWith('0')) p = '62' + p.slice(1);
  return p;
}

function orderankuWaUrl(order) {
  const phone = orderankuWaPhone(order?.customer_phone);
  if (!phone) return '';
  const message = orderankuWaText(order);
  return `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
}

async function checkOrderankuWhatsapp(order, target, statusTarget) {
  const phone = orderankuWaPhone(order?.customer_phone);
  if (!phone) {
    showToast('Nomor WhatsApp pelanggan tidak tersedia');
    return;
  }
  const user = typeof telegramUser === 'function' ? telegramUser() : (window.Telegram?.WebApp?.initDataUnsafe?.user || null);
  if (!user?.id) {
    showToast('Mini App harus dibuka dari Telegram');
    return;
  }
  target.innerHTML = '<b>⏳ MENGECEK WHATSAPP...</b><span>Mohon tunggu</span>';
  target.disabled = true;
  try {
    const qs = new URLSearchParams({ telegram_id: String(user.id), phone });
    const r = await fetch('/api/whatsapp-check?' + qs.toString(), { cache: 'no-store' });
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.message || d.error || 'Validasi gagal');
    target.disabled = false;
    target.innerHTML = '<b>🔍 CEK WA</b><span>Validasi ›</span>';
    setOrderankuWaStatus(order, d.exists_whatsapp, d.checked_at);
    if (statusTarget) statusTarget.textContent = orderankuWaStatusHtml(order);
    if (d.exists_whatsapp) {
      target.dataset.valid = '1';
      showToast('Nomor WhatsApp valid dan terdaftar');
    } else {
      target.dataset.valid = '0';
      showToast('Nomor tidak terdaftar di WhatsApp');
    }
  } catch (e) {
    target.disabled = false;
    target.innerHTML = '<b>🔍 CEK WA</b><span>Validasi ›</span>';
    showToast('Gagal cek WA: ' + e.message);
  }
}

function openOrderankuWhatsapp(order) {
  const url = orderankuWaUrl(order);
  if (!url) {
    showToast('Nomor WhatsApp pelanggan tidak tersedia');
    return;
  }
  if (window.Telegram?.WebApp?.openLink) {
    window.Telegram.WebApp.openLink(url);
  } else {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

function jagirSubarea(order) {
  const address = String(order?.address || '').toUpperCase();
  if (address.includes('RUNGKUT')) return 'RUNGKUT';
  if (address.includes('GUNUNG ANYAR') || address.includes('SINGARAJA')) return 'GUNUNG ANYAR';
  if (address.includes('MEDOKAN')) return 'MEDOKAN';
  return 'LAINNYA';
}

function isJagirArea(area) {
  if (String(area?.area || '').toUpperCase() === 'JAGIR') return true;
  return (area?.orders || []).some(o => String(o.sto || '').toUpperCase() === 'JGR' || String(o.source || '').toUpperCase().includes('JAGIR'));
}

function filterPill(label, active, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = label;
  b.style.cssText = `border:1px solid ${active ? '#55d9ff' : '#294562'};background:${active ? '#103453' : '#0a1929'};color:${active ? '#dff8ff' : '#91a7bd'};border-radius:999px;padding:8px 11px;font-size:10px;font-weight:700;white-space:nowrap;cursor:pointer`;
  b.addEventListener('click', onClick);
  return b;
}

function renderFilterRow(items) {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:7px;overflow-x:auto;padding:2px 0 9px;scrollbar-width:none';
  items.forEach(i => row.appendChild(filterPill(i.label, i.active, i.onClick)));
  return row;
}

function orderCard(area, order, index) {
  const button = document.createElement('button');
  button.className = 'mini-order';
  button.type = 'button';
  button.style.width = '100%';
  button.style.textAlign = 'left';
  button.style.cursor = 'pointer';
  button.style.color = 'inherit';
  const source = String(order.source || '').toUpperCase().includes('JAGIR') || String(order.sto || '').toUpperCase() === 'JGR' ? 'WO JAGIR' : 'ORDER SHEET';
  button.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
    <div style="min-width:0;flex:1">
      <strong>${index + 1}. ${esc(order.customer_name || '-')}</strong>
      <small style="line-height:1.65">🏷 ${esc(source)} • ${esc(order.sto || (source === 'WO JAGIR' ? 'JGR' : 'MYR'))}<br>🎫 ${esc(order.ticket_id || 'MANUAL')}<br>🌐 ${esc(order.service_number || '-')}<br>📞 ${esc(order.customer_phone || '-')}<br>⚡ ${esc(order.package || '-')}<br>📡 ONU RX: ${esc(order.onu_rx || '-')}<br>📝 RCA: ${esc(order.rca || '-')}<br>🏠 ${esc(order.address || '-')}</small>
    </div>
    <span style="font-size:22px;color:#55d9ff;line-height:1">›</span>
  </div>`;
  button.addEventListener('click', () => renderMyOrderDetail(area, order, index));
  return button;
}

function renderMyOrderDetail(area, order, index) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  if (!list || !count) return;
  count.textContent = 'DETAIL ORDER';
  list.replaceChildren();

  const back = document.createElement('button');
  back.className = 'tool-action';
  back.innerHTML = `<b>‹ Kembali ke ${esc(area.area)}</b><span>📍</span>`;
  back.addEventListener('click', () => renderMyOpenArea(area));
  list.appendChild(back);

  const source = String(order.source || '').toUpperCase().includes('JAGIR') || String(order.sto || '').toUpperCase() === 'JGR' ? 'WORK ORDER JAGIR' : 'ORDER SHEET';
  const card = document.createElement('article');
  card.className = 'tool-card';
  card.innerHTML = `
    <strong>${index + 1}. ${esc(order.customer_name || '-')}</strong>
    <small>Detail order OPEN • ${esc(source)} • ${esc(order.sto || (source === 'WORK ORDER JAGIR' ? 'JGR' : 'MYR'))}</small>
    <div style="margin-top:12px">
      <div class="info-box"><span>🎫</span><p><strong>${esc(order.ticket_id || 'MANUAL')}</strong><br>Tiket</p></div>
      <div style="margin-top:10px;font-size:11px;line-height:1.75;color:#9fb2c6">
        🌐 <b style="color:#edf6ff">${esc(order.service_number || '-')}</b><br>
        📞 ${esc(order.customer_phone || '-')}<br>
        ⚡ ${esc(order.package || '-')}<br>
        📡 ONU RX: ${esc(order.onu_rx || '-')}<br>
        🧾 SN ONT LAMA: ${esc(order.old_sn || '-')}<br>
        📦 TYPE ONT: ${esc(order.ont_type || '-')}<br>
        📝 RCA: ${esc(order.rca || '-')}<br>
        👷 Assign: ${esc(order.assigned_technician || state.myOpenOrders?.technician?.name || '-')}<br>
        ${order.odp_name ? `📍 ODP: ${esc(order.odp_name)}<br>` : ''}
        🏠 ${esc(order.address || '-')}
      </div>
    </div>
    <button class="tool-action" id="orderCopyWa" type="button"><b>💬 SALIN FORMAT WA</b><span>Salin ›</span></button>
    <button class="tool-action" id="orderSendWa" type="button"><b>📲 KIRIM PESAN</b><span>WhatsApp ›</span></button>
    <div id="orderWaStatus" style="margin:10px 0 2px;padding:11px 13px;border:1px solid #294562;border-radius:12px;background:#0a1929;color:#dff8ff;font-size:12px;font-weight:800;text-align:center">${orderankuWaStatusHtml(order)}</div>
    <button class="tool-action" id="orderCheckWa" type="button"><b>🔍 CEK WA</b><span>Validasi ›</span></button>
    <button class="tool-action" id="orderStartInput" type="button"><b>＋ KERJAKAN ORDER INI</b><span>Input ›</span></button>`;
  list.appendChild(card);

  card.querySelector('#orderCopyWa')?.addEventListener('click', () => copyText(orderankuWaText(order), 'Format WhatsApp pelanggan tersalin'));
  card.querySelector('#orderSendWa')?.addEventListener('click', () => openOrderankuWhatsapp(order));
  const waStatus = card.querySelector('#orderWaStatus');
  const checkWa = card.querySelector('#orderCheckWa');
  restoreOrderankuWhatsappStatus(order, waStatus);
  checkWa?.addEventListener('click', () => checkOrderankuWhatsapp(order, checkWa, waStatus));
  card.querySelector('#orderStartInput')?.addEventListener('click', () => {
    const selected = { ...order, area: area.area };
    openPage('inputPage');
    renderWorkflowForm('lengkap', selected);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

renderMyOrderAreas = function renderFilteredMyOrderAreas(d) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  if (!list || !count) return;
  list.replaceChildren();

  const allAreas = d?.areas || [];
  const myrAreas = allAreas.filter(a => !isJagirArea(a));
  const jagirAreas = allAreas.filter(isJagirArea);
  const sourceAreas = orderankuFilter.sto === 'MYR' ? myrAreas : orderankuFilter.sto === 'JGR' ? jagirAreas : allAreas;
  const total = sourceAreas.reduce((n, a) => n + (a.orders?.length || 0), 0);
  count.textContent = `${total} OPEN`;

  list.appendChild(renderFilterRow([
    { label: `SEMUA (${d?.total_open || 0})`, active: orderankuFilter.sto === 'ALL', onClick: () => { orderankuFilter.sto = 'ALL'; orderankuFilter.jagirArea = 'ALL'; renderMyOrderAreas(d); } },
    { label: `MANYAR / MYR (${myrAreas.reduce((n,a)=>n+(a.orders?.length||0),0)})`, active: orderankuFilter.sto === 'MYR', onClick: () => { orderankuFilter.sto = 'MYR'; orderankuFilter.jagirArea = 'ALL'; renderMyOrderAreas(d); } },
    { label: `JAGIR / JGR (${jagirAreas.reduce((n,a)=>n+(a.orders?.length||0),0)})`, active: orderankuFilter.sto === 'JGR', onClick: () => { orderankuFilter.sto = 'JGR'; orderankuFilter.jagirArea = 'ALL'; renderMyOrderAreas(d); } },
  ]));

  if (!sourceAreas.length) {
    list.insertAdjacentHTML('beforeend', '<div class="empty"><p>✅ Tidak ada order OPEN pada filter ini.</p></div>');
    return;
  }

  if (orderankuFilter.sto === 'JGR') {
    const jagirOrders = jagirAreas.flatMap(a => (a.orders || []).map(o => ({ ...o, __area: a })));
    const counts = {};
    jagirOrders.forEach(({__area, ...o}) => { const k = jagirSubarea(o); counts[k] = (counts[k] || 0) + 1; });
    const subareas = ['RUNGKUT', 'GUNUNG ANYAR', 'MEDOKAN', 'LAINNYA'].filter(k => counts[k]);
    list.appendChild(renderFilterRow([
      { label: `SEMUA (${jagirOrders.length})`, active: orderankuFilter.jagirArea === 'ALL', onClick: () => { orderankuFilter.jagirArea = 'ALL'; renderMyOrderAreas(d); } },
      ...subareas.map(k => ({ label: `${k} (${counts[k]})`, active: orderankuFilter.jagirArea === k, onClick: () => { orderankuFilter.jagirArea = k; renderMyOrderAreas(d); } }))
    ]));

    const filtered = jagirOrders.filter(({__area, ...o}) => orderankuFilter.jagirArea === 'ALL' || jagirSubarea(o) === orderankuFilter.jagirArea);
    count.textContent = `${filtered.length} OPEN`;
    filtered.forEach(({__area, ...order}, index) => list.appendChild(orderCard(__area, order, index)));
    return;
  }

  sourceAreas.forEach((a, areaIndex) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tool-action order-area-button';
    b.dataset.areaIndex = String(allAreas.indexOf(a));
    b.innerHTML = `<div><b>📍 ${esc(a.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${fmt(a.open)} | 🔴 Close: ${fmt(a.close)}${a.update ? ` | 🟡 Update: ${fmt(a.update)}` : ''}</small></div><span>${fmt(a.open)} ›</span>`;
    b.addEventListener('click', () => renderMyOpenArea(a));
    list.appendChild(b);
  });
};

renderMyOpenArea = function renderClickableMyOpenArea(area) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  if (!list || !count || !area) return;
  list.replaceChildren();
  count.textContent = `${area.orders?.length || 0} OPEN`;

  const back = document.createElement('button');
  back.type = 'button';
  back.className = 'tool-action';
  back.innerHTML = '<b>‹ Kembali ke daftar area</b><span>📍</span>';
  back.addEventListener('click', () => renderMyOrderAreas(state.myOpenOrders));
  list.appendChild(back);

  let orders = area.orders || [];
  if (isJagirArea(area)) {
    const counts = {};
    orders.forEach(o => { const k = jagirSubarea(o); counts[k] = (counts[k] || 0) + 1; });
    const subareas = ['RUNGKUT', 'GUNUNG ANYAR', 'MEDOKAN', 'LAINNYA'].filter(k => counts[k]);
    list.appendChild(renderFilterRow([
      { label: `SEMUA (${orders.length})`, active: orderankuFilter.jagirArea === 'ALL', onClick: () => { orderankuFilter.jagirArea = 'ALL'; renderMyOpenArea(area); } },
      ...subareas.map(k => ({ label: `${k} (${counts[k]})`, active: orderankuFilter.jagirArea === k, onClick: () => { orderankuFilter.jagirArea = k; renderMyOpenArea(area); } }))
    ]));
    orders = orders.filter(o => orderankuFilter.jagirArea === 'ALL' || jagirSubarea(o) === orderankuFilter.jagirArea);
    count.textContent = `${orders.length} OPEN`;
  }

  orders.forEach((order, index) => list.appendChild(orderCard(area, order, index)));
};

// Fallback delegation: keeps area navigation working even if another enhancement
// re-renders/replaces Orderanku buttons after this script has bound listeners.
if (!window.__orderAreaDelegationInstalled) {
  window.__orderAreaDelegationInstalled = true;
  document.addEventListener('click', event => {
    const button = event.target.closest?.('#myOrdersList .order-area-button[data-area-index]');
    if (!button) return;
    const index = Number(button.dataset.areaIndex);
    const area = state.myOpenOrders?.areas?.[index];
    if (!area) return;
    event.preventDefault();
    event.stopPropagation();
    renderMyOpenArea(area);
  }, true);
}
