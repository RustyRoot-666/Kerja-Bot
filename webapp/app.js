const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const state = {
  area: 'ALL',
  period: 'daily',
  query: '',
  payload: null,
  me: null,
  myOpenOrders: null,
};

const fmt = value => new Intl.NumberFormat('id-ID').format(Number(value || 0));
const shortDay = value => String(value || '').slice(0, 3).toUpperCase();
const normName = value => String(value || '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim().replace(/\s+/g, ' ');

function telegramUser() {
  return tg?.initDataUnsafe?.user || null;
}

function telegramName() {
  const user = telegramUser();
  if (!user) return '';
  return [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
}

function setWelcome() {
  const name = telegramName() || 'Teknisi';
  document.querySelector('#welcomeName').textContent = name;
  const now = new Date();
  const date = new Intl.DateTimeFormat('id-ID', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(now).replace(' pukul ', ' • ');
  document.querySelector('#currentDate').textContent = `▣ ${date} WIB`;
}

function selectedRows() {
  const rows = state.payload?.leaderboard || [];
  const q = state.query.trim().toUpperCase();
  if (!q) return rows;
  return rows.filter(item =>
    String(item.name || '').toUpperCase().includes(q) ||
    String(item.nik || '').toUpperCase().includes(q)
  );
}

function periodText() {
  return state.period === 'daily' ? 'Hari Ini' : state.period === 'weekly' ? 'Minggu Ini' : 'Keseluruhan';
}

function renderSummary() {
  const s = state.payload?.summary || {};
  const close = Number(s.total_close || 0);
  const tech = Number(s.active_technicians || 0);
  const avg = Number(s.average_close || 0);
  document.querySelector('#totalClose').textContent = fmt(close);
  document.querySelector('#activeTechnicians').textContent = fmt(tech);
  document.querySelector('#averageClose').textContent = avg.toFixed(1).replace('.0', '');
  document.querySelector('#periodLabel').textContent = state.payload?.period_label || periodText();
  document.querySelector('#periodPillLabel').textContent = periodText();
  document.querySelector('#activeAreaLabel').textContent = state.area === 'MYR' ? 'MANYAR' : state.area === 'JGR' ? 'JAGIR' : 'SEMUA';
  document.querySelector('#ringValue').textContent = fmt(close);
  document.querySelector('#ringClose').textContent = fmt(close);
  document.querySelector('#ringTech').textContent = fmt(tech);
  document.querySelector('#ringAvg').textContent = avg.toFixed(1).replace('.0', '');
  const degree = Math.min(360, Math.max(20, close * 7));
  document.querySelector('#progressRing').style.setProperty('--p', `${degree}deg`);
}

function renderTrend() {
  const chart = document.querySelector('#trendChart');
  chart.replaceChildren();
  const trend = state.payload?.trend || [];
  const max = Math.max(1, ...trend.map(item => Number(item.total || 0)));
  const total = trend.reduce((sum, item) => sum + Number(item.total || 0), 0);
  document.querySelector('#trendTotal').textContent = `${fmt(total)} close`;
  for (const item of trend) {
    const col = document.createElement('div');
    col.className = 'trend-col';
    const height = Math.max(5, Math.round((Number(item.total || 0) / max) * 100));
    col.innerHTML = `<span class="trend-value">${fmt(item.total)}</span><div class="trend-bar-wrap"><div class="trend-bar" style="height:${height}%"></div></div><span class="trend-label">${shortDay(item.label)}</span>`;
    chart.appendChild(col);
  }
}

function rankLabel(index) {
  if (index === 0) return '1';
  if (index === 1) return '2';
  if (index === 2) return '3';
  return String(index + 1);
}

function renderLeaderboard() {
  const list = document.querySelector('#leaderboard');
  const empty = document.querySelector('#emptyState');
  const template = document.querySelector('#leaderTemplate');
  const rows = selectedRows();
  list.replaceChildren();
  document.querySelector('#resultCount').textContent = `${rows.length} teknisi`;
  empty.classList.toggle('hidden', rows.length > 0);
  rows.slice(0, 12).forEach((item, index) => {
    const node = template.content.cloneNode(true);
    const button = node.querySelector('.leader-row');
    node.querySelector('.rank').textContent = rankLabel(index);
    node.querySelector('.leader-name').textContent = item.name || '-';
    node.querySelector('.leader-meta').textContent = `${item.nik || '-'} • ${item.area_label || item.sto || 'SEMUA'}`;
    node.querySelector('.leader-score').textContent = fmt(item.total);
    button.addEventListener('click', () => openTechnician(item.key || item.nik));
    list.appendChild(node);
  });
}

function renderRecentActivity() {
  const container = document.querySelector('#recentActivity');
  const rows = state.payload?.leaderboard || [];
  container.replaceChildren();
  if (!rows.length) {
    container.innerHTML = '<div class="empty"><p>Belum ada aktivitas pada filter ini.</p></div>';
    return;
  }
  rows.slice(0, 3).forEach((item, idx) => {
    const row = document.createElement('div');
    row.className = 'activity-item';
    row.innerHTML = `<span class="activity-bullet">${idx === 0 ? '✓' : '↗'}</span><div><strong>${item.name || '-'}</strong><small>${fmt(item.total)} close • ${item.area_label || item.sto || 'SEMUA'}</small></div>`;
    container.appendChild(row);
  });
}

function renderRca() {
  const box = document.querySelector('.rca-panel .placeholder-chart');
  if (!box) return;
  const summary = state.payload?.rca_summary || { total: 0, items: [] };
  const items = summary.items || [];
  if (!summary.total || !items.length) {
    box.innerHTML = `<div class="placeholder-pie">!</div><div><strong>Belum ada RCA</strong><p>Belum ditemukan RCA pada Google Sheet maupun Grup Kendala untuk filter area ini.</p></div>`;
    return;
  }

  const palette = ['#8d2dce', '#ee4f5d', '#ffb62c', '#2584ef', '#2bd08f', '#57e6ff', '#7e74ff', '#ff7d20', '#8ca2bd'];
  let cursor = 0;
  const stops = [];
  items.forEach((item, index) => {
    const start = cursor;
    cursor += Number(item.percent || 0);
    stops.push(`${palette[index % palette.length]} ${start}% ${cursor}%`);
  });
  if (cursor < 100) stops.push(`#1a2e45 ${cursor}% 100%`);

  const legend = items.slice(0, 7).map((item, index) => `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin:7px 0;font-size:10px">
      <span style="display:flex;align-items:center;gap:7px;color:#b7c8d9"><i style="width:8px;height:8px;border-radius:50%;background:${palette[index % palette.length]};display:inline-block"></i>${item.label}</span>
      <strong style="white-space:nowrap">${fmt(item.count)} <span style="color:#71879f;font-weight:500">(${item.percent}%)</span></strong>
    </div>`).join('');

  box.innerHTML = `
    <div class="placeholder-pie" style="width:180px;height:180px;flex:0 0 180px;font-size:24px;background:conic-gradient(${stops.join(',')});box-shadow:inset 0 0 0 38px #0a1929">${fmt(summary.total)}</div>
    <div style="min-width:0;flex:1">
      <strong>${fmt(summary.total)} RCA tercatat</strong>
      <p style="margin:4px 0 8px">${summary.source || 'Google Sheet + Grup Kendala'} • Sheet ${fmt(summary.sheet_count)} • Kendala ${fmt(summary.kendala_count)}</p>
      ${legend}
    </div>`;
}

function render() {
  renderSummary();
  renderTrend();
  renderLeaderboard();
  renderRecentActivity();
  renderRca();
}

function resolveMeFromPayload() {
  const rows = state.payload?.leaderboard || [];
  const tgName = normName(telegramName());
  if (!tgName) return null;
  return rows.find(item => normName(item.name) === tgName) || null;
}

async function loadDashboard() {
  const params = new URLSearchParams({ area: state.area, period: state.period });
  try {
    const response = await fetch(`/api/dashboard?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    state.me = resolveMeFromPayload() || state.me;
  } catch (error) {
    console.error('Gagal mengambil dashboard', error);
    state.payload = { summary: { total_close: 0, active_technicians: 0, average_close: 0 }, period_label: 'Data tidak tersedia', trend: [], leaderboard: [], rca_summary: { total: 0, items: [] } };
  }
  render();
}

async function fetchTechnician(key, area = 'ALL') {
  const params = new URLSearchParams({ key, area });
  const response = await fetch(`/api/technician?${params}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function openTechnician(key) {
  try {
    const data = await fetchTechnician(key, state.area);
    document.querySelector('#detailName').textContent = data.name || '-';
    document.querySelector('#detailNik').textContent = `NIK ${data.nik || '-'}`;
    document.querySelector('#detailDaily').textContent = fmt(data.daily);
    document.querySelector('#detailWeekly').textContent = fmt(data.weekly);
    document.querySelector('#detailAll').textContent = fmt(data.all);
    document.querySelector('#detailCount').textContent = `${(data.orders || []).length} data`;
    const container = document.querySelector('#detailOrders');
    container.replaceChildren();
    for (const order of data.orders || []) {
      const row = document.createElement('div');
      row.className = 'order-row';
      row.innerHTML = `<div><strong>${order.service_number || '-'}</strong><small>${order.ticket_id || 'MANUAL'} • ${order.area_label || order.sto || '-'}</small></div><span class="order-date">${order.date_label || '-'}</span>`;
      container.appendChild(row);
    }
    document.querySelector('#detailPanel').classList.remove('hidden');
  } catch (error) {
    console.error('Gagal membuka detail teknisi', error);
    showToast('Detail teknisi gagal dimuat');
  }
}

function setMyOrderSummary(totalOpen, activeAreas) {
  const boxes = document.querySelectorAll('#myOrderSummary > div');
  const labels = ['ORDER OPEN', 'AREA AKTIF', 'SUMBER'];
  const values = [fmt(totalOpen), fmt(activeAreas), 'SHEET'];
  boxes.forEach((box, index) => {
    box.querySelector('span').textContent = labels[index];
    box.querySelector('strong').textContent = values[index];
  });
}

function renderMyOrderAreas(data) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  list.replaceChildren();
  count.textContent = `${data.total_open || 0} OPEN`;
  if (!data.areas?.length) {
    list.innerHTML = '<div class="empty"><p>✅ Tidak ada order OPEN dari Google Sheets.</p></div>';
    return;
  }
  data.areas.forEach(area => {
    const button = document.createElement('button');
    button.className = 'tool-action';
    button.innerHTML = `<div><b>📍 ${area.area}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${fmt(area.open)} | 🔴 Close: ${fmt(area.close)}${area.update ? ` | 🟡 Update: ${fmt(area.update)}` : ''}</small></div><span>${fmt(area.open)} ›</span>`;
    button.addEventListener('click', () => renderMyOpenArea(area));
    list.appendChild(button);
  });
}

function renderMyOpenArea(area) {
  const list = document.querySelector('#myOrdersList');
  const count = document.querySelector('#myOrderCount');
  list.replaceChildren();
  count.textContent = `${area.orders?.length || 0} OPEN`;

  const back = document.createElement('button');
  back.className = 'tool-action';
  back.innerHTML = '<b>‹ Kembali ke daftar area</b><span>📍</span>';
  back.addEventListener('click', () => renderMyOrderAreas(state.myOpenOrders));
  list.appendChild(back);

  const heading = document.createElement('div');
  heading.className = 'tool-card';
  heading.innerHTML = `<strong>🟢 ORDER OPEN — ${area.area}</strong><small>${state.myOpenOrders?.technician?.name || '-'} • ${fmt(area.orders?.length || 0)} order</small>`;
  list.appendChild(heading);

  (area.orders || []).forEach((order, index) => {
    const card = document.createElement('div');
    card.className = 'mini-order';
    card.innerHTML = `
      <strong>${index + 1}. ${order.customer_name || '-'}</strong>
      <small style="line-height:1.65">
        🎫 ${order.ticket_id || 'MANUAL'}<br>
        🌐 ${order.service_number || '-'}<br>
        📞 ${order.customer_phone || '-'}<br>
        ⚡ ${order.package || '-'}<br>
        📡 ONU RX: ${order.onu_rx || '-'}<br>
        📝 RCA: ${order.rca || '-'}<br>
        🏠 ${order.address || '-'}
      </small>`;
    list.appendChild(card);
  });
}

async function loadMyOpenOrders(force = false) {
  const user = telegramUser();
  const identity = document.querySelector('#ordersIdentity');
  const list = document.querySelector('#myOrdersList');
  if (!user?.id) {
    identity.textContent = 'Mini App harus dibuka dari Telegram untuk membaca akun teknisi.';
    list.innerHTML = '<div class="empty"><p>Telegram ID tidak tersedia.</p></div>';
    return;
  }

  identity.textContent = '🔄 Membaca Google Sheets terbaru...';
  list.innerHTML = '<div class="empty"><p>Memuat order OPEN...</p></div>';
  try {
    const params = new URLSearchParams({ telegram_id: String(user.id) });
    if (force) params.set('force', '1');
    const response = await fetch(`/api/my-open-orders?${params}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`);
    state.myOpenOrders = data;
    identity.textContent = `${data.technician.name} • NIK ${data.technician.nik || '-'} • ${data.source}`;
    setMyOrderSummary(data.total_open, data.active_areas);
    renderMyOrderAreas(data);
  } catch (error) {
    console.error('Gagal memuat Orderanku dari Sheet', error);
    identity.textContent = '❌ Gagal membaca Orderanku dari Google Sheets.';
    list.innerHTML = `<div class="empty"><p>${error.message || 'Gagal membaca data.'}</p></div>`;
    setMyOrderSummary(0, 0);
  }
}

async function loadReportData() {
  const candidate = state.me || resolveMeFromPayload();
  const reportIdentity = document.querySelector('#reportIdentity');
  if (!candidate) {
    reportIdentity.textContent = 'Data akun Telegram ini belum cocok dengan nama teknisi pada REPORT.';
    return;
  }
  try {
    const data = await fetchTechnician(candidate.key || candidate.nik, 'ALL');
    state.me = candidate;
    reportIdentity.textContent = `${data.name || candidate.name} • NIK ${data.nik || candidate.nik || '-'}`;
    document.querySelectorAll('#reportSummary strong').forEach((el, i) => el.textContent = fmt([data.daily, data.weekly, data.all][i]));
  } catch (error) {
    console.error('Gagal memuat laporan pribadi', error);
    reportIdentity.textContent = 'Gagal memuat data teknisi.';
  }
}

function openPage(pageId, button = null) {
  document.querySelectorAll('.page-view').forEach(page => page.classList.toggle('hidden', page.id !== pageId));
  document.querySelectorAll('.nav-item[data-page]').forEach(item => item.classList.toggle('active', item.dataset.page === pageId));
  if (pageId === 'ordersPage') loadMyOpenOrders();
  if (pageId === 'reportsPage') loadReportData();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function selectArea(value) {
  state.area = value;
  document.querySelectorAll('.segment').forEach(item => item.classList.toggle('active', item.dataset.area === value));
  loadDashboard();
}

function showToast(text) {
  const toast = document.querySelector('#toast');
  toast.textContent = text;
  toast.classList.remove('hidden');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add('hidden'), 1800);
}

async function copyCommand(command) {
  try {
    await navigator.clipboard.writeText(command);
    showToast(`${command} tersalin`);
  } catch {
    const area = document.createElement('textarea');
    area.value = command;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    showToast(`${command} tersalin`);
  }
  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
}

function closeOverlays() {
  document.querySelector('#drawer').classList.add('hidden');
  document.querySelector('#moreMenu').classList.add('hidden');
}

document.querySelectorAll('.segment').forEach(button => button.addEventListener('click', () => selectArea(button.dataset.area)));
document.querySelectorAll('[data-area-shortcut]').forEach(button => button.addEventListener('click', () => selectArea(button.dataset.areaShortcut)));
document.querySelectorAll('.period').forEach(button => {
  button.addEventListener('click', () => {
    state.period = button.dataset.period;
    document.querySelectorAll('.period').forEach(item => item.classList.toggle('active', item === button));
    loadDashboard();
  });
});
document.querySelector('#searchInput').addEventListener('input', event => { state.query = event.target.value; renderLeaderboard(); });
document.querySelectorAll('.nav-item[data-page]').forEach(button => button.addEventListener('click', () => openPage(button.dataset.page, button)));
document.querySelectorAll('[data-back-dashboard]').forEach(button => button.addEventListener('click', () => openPage('dashboardPage')));
document.querySelectorAll('[data-close-detail]').forEach(item => item.addEventListener('click', () => document.querySelector('#detailPanel').classList.add('hidden')));
document.querySelectorAll('[data-copy-command]').forEach(button => button.addEventListener('click', () => copyCommand(button.dataset.copyCommand)));

document.querySelector('#menuButton')?.addEventListener('click', () => document.querySelector('#drawer').classList.remove('hidden'));
document.querySelectorAll('[data-close-drawer]').forEach(item => item.addEventListener('click', closeOverlays));
document.querySelectorAll('[data-drawer-page]').forEach(button => button.addEventListener('click', () => { closeOverlays(); openPage(button.dataset.drawerPage); }));
document.querySelector('#moreButton')?.addEventListener('click', () => document.querySelector('#moreMenu').classList.remove('hidden'));
document.querySelectorAll('[data-close-more]').forEach(item => item.addEventListener('click', closeOverlays));
document.querySelector('#refreshButton')?.addEventListener('click', async () => {
  closeOverlays();
  await loadDashboard();
  if (!document.querySelector('#ordersPage').classList.contains('hidden')) await loadMyOpenOrders(true);
  if (!document.querySelector('#reportsPage').classList.contains('hidden')) await loadReportData();
  showToast('Data diperbarui');
});
document.querySelector('#closeMiniAppButton')?.addEventListener('click', () => { if (tg?.close) tg.close(); });

setWelcome();
loadDashboard();