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
};

function fmt(value) {
  return new Intl.NumberFormat('id-ID').format(Number(value || 0));
}

function shortDay(value) {
  return String(value || '').slice(0, 3).toUpperCase();
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

function renderSummary() {
  const s = state.payload?.summary || {};
  document.querySelector('#totalClose').textContent = fmt(s.total_close);
  document.querySelector('#activeTechnicians').textContent = fmt(s.active_technicians);
  document.querySelector('#averageClose').textContent = Number(s.average_close || 0).toFixed(1).replace('.0', '');
  document.querySelector('#periodLabel').textContent = state.payload?.period_label || '-';
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
    const height = Math.max(4, Math.round((Number(item.total || 0) / max) * 100));
    col.innerHTML = `
      <span class="trend-value">${fmt(item.total)}</span>
      <div class="trend-bar-wrap"><div class="trend-bar" style="height:${height}%"></div></div>
      <span class="trend-label">${shortDay(item.label)}</span>
    `;
    chart.appendChild(col);
  }
}

function rankLabel(index) {
  if (index === 0) return '🥇';
  if (index === 1) return '🥈';
  if (index === 2) return '🥉';
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

  rows.forEach((item, index) => {
    const node = template.content.cloneNode(true);
    const button = node.querySelector('.leader-row');
    node.querySelector('.rank').textContent = rankLabel(index);
    node.querySelector('.leader-name').textContent = item.name || '-';
    node.querySelector('.leader-meta').textContent = `${item.nik || '-'} • ${item.area_label || item.sto || 'SEMUA'}`;
    node.querySelector('.leader-score').textContent = fmt(item.total);
    button.addEventListener('click', () => openTechnician(item.nik));
    list.appendChild(node);
  });
}

function render() {
  renderSummary();
  renderTrend();
  renderLeaderboard();
}

async function loadDashboard() {
  const params = new URLSearchParams({ area: state.area, period: state.period });
  try {
    const response = await fetch(`/api/dashboard?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
  } catch (error) {
    console.error('Gagal mengambil dashboard', error);
    state.payload = {
      summary: { total_close: 0, active_technicians: 0, average_close: 0 },
      period_label: 'Data tidak tersedia',
      trend: [],
      leaderboard: [],
    };
  }
  render();
}

async function openTechnician(nik) {
  try {
    const params = new URLSearchParams({ nik, area: state.area });
    const response = await fetch(`/api/technician?${params}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
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
      row.innerHTML = `
        <div>
          <strong>${order.service_number || '-'}</strong>
          <small>${order.ticket_id || 'MANUAL'} • ${order.area_label || order.sto || '-'}</small>
        </div>
        <span class="order-date">${order.date_label || '-'}</span>
      `;
      container.appendChild(row);
    }
    document.querySelector('#detailPanel').classList.remove('hidden');
  } catch (error) {
    console.error('Gagal membuka detail teknisi', error);
  }
}

document.querySelectorAll('.segment').forEach(button => {
  button.addEventListener('click', () => {
    state.area = button.dataset.area;
    document.querySelectorAll('.segment').forEach(item => item.classList.toggle('active', item === button));
    loadDashboard();
  });
});

document.querySelectorAll('.period').forEach(button => {
  button.addEventListener('click', () => {
    state.period = button.dataset.period;
    document.querySelectorAll('.period').forEach(item => item.classList.toggle('active', item === button));
    loadDashboard();
  });
});

document.querySelector('#searchInput').addEventListener('input', event => {
  state.query = event.target.value;
  renderLeaderboard();
});

document.querySelectorAll('[data-close-detail]').forEach(item => {
  item.addEventListener('click', () => document.querySelector('#detailPanel').classList.add('hidden'));
});

loadDashboard();
