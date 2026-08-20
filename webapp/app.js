const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const state = { items: [], filter: 'all', query: '' };
const rupiah = new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 });

function normalizeStatus(value) {
  return String(value || '').trim().toUpperCase();
}

function isPaid(item) {
  const status = normalizeStatus(item.status_payment || item.payment_status);
  return ['PAID', 'TERBAYAR', 'SUDAH BAYAR', 'SUCCESS'].includes(status);
}

function amountOf(item) {
  const raw = item.amount ?? item.batch_tacticalpro ?? item.nominal ?? 0;
  if (typeof raw === 'number') return raw;
  return Number(String(raw).replace(/[^0-9]/g, '')) || 0;
}

function renderSummary() {
  const total = state.items.reduce((sum, item) => sum + amountOf(item), 0);
  const paid = state.items.filter(isPaid);
  const unpaid = state.items.filter(item => !isPaid(item));
  const paidTotal = paid.reduce((sum, item) => sum + amountOf(item), 0);
  const unpaidTotal = unpaid.reduce((sum, item) => sum + amountOf(item), 0);

  document.querySelector('#totalIncome').textContent = rupiah.format(total);
  document.querySelector('#paidIncome').textContent = rupiah.format(paidTotal);
  document.querySelector('#unpaidIncome').textContent = rupiah.format(unpaidTotal);
  document.querySelector('#totalOrders').textContent = `${state.items.length} order`;
  document.querySelector('#paidCount').textContent = `${paid.length} order`;
  document.querySelector('#unpaidCount').textContent = `${unpaid.length} order`;
}

function filteredItems() {
  return state.items.filter(item => {
    const paid = isPaid(item);
    if (state.filter === 'paid' && !paid) return false;
    if (state.filter === 'unpaid' && paid) return false;
    if (state.query && !String(item.no_inet || item.inet || '').includes(state.query)) return false;
    return true;
  });
}

function renderList() {
  const list = document.querySelector('#paymentList');
  const empty = document.querySelector('#emptyState');
  const template = document.querySelector('#paymentTemplate');
  const items = filteredItems();
  list.replaceChildren();
  document.querySelector('#resultCount').textContent = `${items.length} data`;

  empty.classList.toggle('hidden', items.length > 0);
  for (const item of items) {
    const card = template.content.cloneNode(true);
    const paid = isPaid(item);
    card.querySelector('.inet').textContent = item.no_inet || item.inet || '-';
    card.querySelector('.work-status').textContent = item.status_tacpro || item.work_status || '-';
    card.querySelector('.task-payment').textContent = item.task_payment || '-';
    card.querySelector('.amount').textContent = rupiah.format(amountOf(item));
    const badge = card.querySelector('.badge');
    badge.textContent = paid ? 'TERBAYAR' : 'BELUM TERBAYAR';
    badge.classList.add(paid ? 'paid' : 'unpaid');
    list.appendChild(card);
  }
}

function render() {
  renderSummary();
  renderList();
}

async function loadData() {
  try {
    const response = await fetch('/api/payments', { cache: 'no-store' });
    const payload = await response.json();
    state.items = Array.isArray(payload.items) ? payload.items : [];
  } catch (error) {
    console.error('Gagal mengambil data pembayaran', error);
    state.items = [];
  }
  render();
}

const telegramUser = tg?.initDataUnsafe?.user;
document.querySelector('#technicianName').textContent = telegramUser
  ? [telegramUser.first_name, telegramUser.last_name].filter(Boolean).join(' ')
  : 'Dashboard teknisi';

document.querySelectorAll('.filter').forEach(button => {
  button.addEventListener('click', () => {
    state.filter = button.dataset.filter;
    document.querySelectorAll('.filter').forEach(item => item.classList.toggle('active', item === button));
    renderList();
  });
});

document.querySelector('#searchInput').addEventListener('input', event => {
  state.query = event.target.value.replace(/\D/g, '');
  renderList();
});

loadData();
