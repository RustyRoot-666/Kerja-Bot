// Personal report dashboard for the logged-in Telegram technician.
// Uses telegram_id -> technicians registry on the backend, so it does not rely
// on the Telegram display name matching REPORT text.

let reportPeriod = 'weekly';
let reportPayload = null;

function buildReportPage() {
  const page = document.querySelector('#reportsPage');
  if (!page) return;
  page.innerHTML = `
    <header class="app-header">
      <button class="round-btn" data-back-dashboard>‹</button>
      <div class="brand-center"><strong>Laporan</strong><small>rekap pekerjaan</small></div>
      <span class="round-btn ghost">▥</span>
    </header>
    <h1 class="tool-title">Rekap Pekerjaan</h1>
    <p class="tool-sub" id="reportIdentity">Memuat data teknisi...</p>

    <div id="reportSummary" class="my-summary">
      <div><span>HARI INI</span><strong>0</strong></div>
      <div><span>MINGGU</span><strong>0</strong></div>
      <div><span>KESELURUHAN</span><strong>0</strong></div>
    </div>

    <section class="panel" style="margin-bottom:12px">
      <div class="panel-head">
        <div><span class="panel-icon">⌁</span><strong>GRAFIK PEROLEHAN 7 HARI</strong></div>
        <span id="personalTrendTotal" class="panel-meta">0 order</span>
      </div>
      <div id="personalTrendChart" class="trend-chart" style="min-height:180px"></div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div><span class="panel-icon">✓</span><strong>SUDAH DIKERJAKAN</strong></div>
        <span id="reportOrderCount" class="panel-meta">0 data</span>
      </div>
      <div class="segmented" style="margin:12px 0">
        <button class="report-period" data-report-period="daily">HARI INI</button>
        <button class="report-period active" data-report-period="weekly">MINGGU</button>
        <button class="report-period" data-report-period="all">SEMUA</button>
      </div>
      <div id="reportOrders" class="mini-order-list"></div>
    </section>`;

  page.querySelector('[data-back-dashboard]')?.addEventListener('click', () => openPage('dashboardPage'));
  page.querySelectorAll('[data-report-period]').forEach(button => {
    button.addEventListener('click', () => {
      reportPeriod = button.dataset.reportPeriod;
      page.querySelectorAll('[data-report-period]').forEach(item => item.classList.toggle('active', item === button));
      renderPersonalReportOrders();
    });
  });
}

function renderPersonalTrend(trend) {
  const chart = document.querySelector('#personalTrendChart');
  if (!chart) return;
  const rows = trend || [];
  const max = Math.max(1, ...rows.map(item => Number(item.total || 0)));
  const total = rows.reduce((sum, item) => sum + Number(item.total || 0), 0);
  document.querySelector('#personalTrendTotal').textContent = `${fmt(total)} order`;
  chart.replaceChildren();
  rows.forEach(item => {
    const col = document.createElement('div');
    col.className = 'trend-col';
    const height = Math.max(5, Math.round(Number(item.total || 0) / max * 100));
    col.innerHTML = `<span class="trend-value">${fmt(item.total)}</span><div class="trend-bar-wrap"><div class="trend-bar" style="height:${height}%"></div></div><span class="trend-label">${esc(item.label || '')}</span>`;
    chart.appendChild(col);
  });
}

function reportOrderMatchesPeriod(order) {
  if (reportPeriod === 'all') return true;
  const raw = String(order.raw_day || order.message_day || '').slice(0, 10);
  const today = new Date();
  const ymd = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  if (reportPeriod === 'daily') return raw ? raw === ymd : String(order.date_label || '').includes(String(today.getDate()));

  // Weekly report follows the bot period: Friday through Thursday.
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const daysSinceFriday = (day.getDay() + 2) % 7;
  const start = new Date(day);
  start.setDate(day.getDate() - daysSinceFriday);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  if (!raw) return true;
  const d = new Date(`${raw}T00:00:00`);
  return d >= start && d <= end;
}

function renderPersonalReportOrders() {
  const box = document.querySelector('#reportOrders');
  const count = document.querySelector('#reportOrderCount');
  if (!box || !count) return;
  const orders = (reportPayload?.orders || []).filter(reportOrderMatchesPeriod);
  count.textContent = `${orders.length} data`;
  box.replaceChildren();
  if (!orders.length) {
    box.innerHTML = '<div class="empty"><p>Belum ada pekerjaan pada periode ini.</p></div>';
    return;
  }
  orders.forEach((order, index) => {
    const row = document.createElement('div');
    row.className = 'mini-order';
    row.innerHTML = `<strong>${index + 1}. 🌐 ${esc(order.service_number || '-')}</strong><small style="line-height:1.7">🎫 ${esc(order.ticket_id || 'MANUAL')}<br>📍 ${esc(order.area_label || order.sto || '-')}<br>📅 ${esc(order.date_label || '-')}</small>`;
    box.appendChild(row);
  });
}

loadReportData = async function loadPersonalReportData() {
  const identity = document.querySelector('#reportIdentity');
  const user = telegramUser();
  if (!user?.id) {
    identity.textContent = 'Mini App harus dibuka dari Telegram.';
    return;
  }
  identity.textContent = '🔄 Memuat rekap pekerjaan...';
  try {
    const response = await fetch(`/api/my-report?${new URLSearchParams({ telegram_id: String(user.id) })}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`);
    reportPayload = data;
    identity.textContent = `${data.technician.name} • NIK ${data.technician.nik || '-'}${data.technician.sto ? ` • ${data.technician.sto}` : ''}`;
    const totals = [data.daily, data.weekly, data.all];
    document.querySelectorAll('#reportSummary strong').forEach((node, i) => node.textContent = fmt(totals[i] || 0));
    renderPersonalTrend(data.trend || []);
    renderPersonalReportOrders();
  } catch (error) {
    reportPayload = null;
    identity.textContent = `❌ ${error.message}`;
    document.querySelectorAll('#reportSummary strong').forEach(node => node.textContent = '0');
    renderPersonalTrend([]);
    renderPersonalReportOrders();
  }
};

buildReportPage();
