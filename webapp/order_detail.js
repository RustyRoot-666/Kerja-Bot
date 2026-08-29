// Clickable Orderanku cards with detail + WhatsApp helper.
// Keeps Orderanku read-only: technicians can inspect Sheet data and copy WA text.

function orderankuWaText(order) {
  if (typeof whatsappCustomerText === 'function') return whatsappCustomerText(order);
  const technician = String(state.myOpenOrders?.technician?.name || telegramName() || 'Teknisi').trim();
  const customer = String(order.customer_name || 'Bapak/Ibu').trim();
  const inet = String(order.service_number || '-').trim();
  const address = String(order.address || '-').trim();
  const phone = String(order.customer_phone || '-').trim();
  const hour = new Date().getHours();
  const greeting = hour < 11 ? 'Selamat pagi' : hour < 15 ? 'Selamat siang' : hour < 18 ? 'Selamat sore' : 'Selamat malam';
  return `${greeting} Bapak/Ibu ${customer}.\n\nPerkenalkan, saya ${technician}, teknisi resmi IndiHome.\n\nMohon maaf mengganggu waktunya. Saya mendapat penugasan dari pihak Telkom untuk melakukan penggantian ONT/Modem pada layanan Bapak/Ibu sebagai bagian dari pembaruan perangkat jaringan.\n\nNo. Internet: ${inet}\nAlamat: ${address}\nNo. HP: ${phone}\n\nDengan penggantian perangkat ini, Bapak/Ibu akan mendapatkan beberapa benefit:\n• Jaringan lebih stabil\n• Perangkat kompatibel dengan jaringan WiFi 5 GHz\n• Biaya langganan tetap, tidak berubah\n• Tidak ada biaya pemasangan / GRATIS\n\nSeluruh proses penggantian dilakukan oleh teknisi resmi dan tidak mengubah paket maupun biaya langganan Bapak/Ibu.\n\nApabila Bapak/Ibu berkenan, mohon konfirmasi waktu yang sesuai agar saya dapat melakukan kunjungan.\n\nJika terdapat kendala atau membutuhkan konfirmasi terkait layanan, Bapak/Ibu dapat menghubungi layanan resmi Telkom melalui 188.\n\nTerima kasih atas perhatian dan kerja sama Bapak/Ibu. 🙏🏼`;
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

  const card = document.createElement('article');
  card.className = 'tool-card';
  card.innerHTML = `
    <strong>${index + 1}. ${esc(order.customer_name || '-')}</strong>
    <small>Detail order OPEN dari Google Sheet</small>
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
        👷 Assign Sheet: ${esc(order.assigned_technician || state.myOpenOrders?.technician?.name || '-')}<br>
        🏠 ${esc(order.address || '-')}
      </div>
    </div>
    <button class="tool-action" id="orderCopyWa" type="button"><b>💬 SALIN FORMAT WA</b><span>Salin ›</span></button>
    <button class="tool-action" id="orderStartInput" type="button"><b>＋ KERJAKAN ORDER INI</b><span>Input ›</span></button>`;
  list.appendChild(card);

  card.querySelector('#orderCopyWa')?.addEventListener('click', () => copyText(orderankuWaText(order), 'Format WhatsApp pelanggan tersalin'));
  card.querySelector('#orderStartInput')?.addEventListener('click', () => {
    const selected = { ...order, area: area.area };
    openPage('inputPage');
    renderWorkflowForm('lengkap', selected);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

renderMyOpenArea = function renderClickableMyOpenArea(area) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  if (!list || !count) return;
  list.replaceChildren();
  count.textContent = `${area.orders?.length || 0} OPEN`;

  const back = document.createElement('button');
  back.className = 'tool-action';
  back.innerHTML = '<b>‹ Kembali ke daftar area</b><span>📍</span>';
  back.addEventListener('click', () => renderMyOrderAreas(state.myOpenOrders));
  list.appendChild(back);

  (area.orders || []).forEach((order, index) => {
    const button = document.createElement('button');
    button.className = 'mini-order';
    button.type = 'button';
    button.style.width = '100%';
    button.style.textAlign = 'left';
    button.style.cursor = 'pointer';
    button.style.color = 'inherit';
    button.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
      <div style="min-width:0;flex:1">
        <strong>${index + 1}. ${esc(order.customer_name || '-')}</strong>
        <small style="line-height:1.65">🎫 ${esc(order.ticket_id || 'MANUAL')}<br>🌐 ${esc(order.service_number || '-')}<br>📞 ${esc(order.customer_phone || '-')}<br>⚡ ${esc(order.package || '-')}<br>📡 ONU RX: ${esc(order.onu_rx || '-')}<br>📝 RCA: ${esc(order.rca || '-')}<br>🏠 ${esc(order.address || '-')}</small>
      </div>
      <span style="font-size:22px;color:#55d9ff;line-height:1">›</span>
    </div>`;
    button.addEventListener('click', () => renderMyOrderDetail(area, order, index));
    list.appendChild(button);
  });
};
