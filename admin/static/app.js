/* ═══════════════════════════════════════════════════════════════════════
   app.js — Painel Hinário CCB
   ═══════════════════════════════════════════════════════════════════════ */
'use strict';

// ── State ─────────────────────────────────────────────────────────────
const state = {
  currentView: 'dashboard',
  videosPage:  1,
  videosTotal: 0,
  videosPages: 1,
  perPage:     20,
  schedulePreview: [],
};

// ── DOM shortcuts ─────────────────────────────────────────────────────
const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ── Toast ─────────────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 3000) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast ${type} show`;
  setTimeout(() => el.classList.remove('show'), duration);
}

// ── View navigation ───────────────────────────────────────────────────
function switchView(name) {
  state.currentView = name;
  $$('.view').forEach(v => v.classList.remove('active'));
  $$('.nav-item').forEach(b => b.classList.remove('active'));
  $(`#view-${name}`).classList.add('active');
  $(`#nav-${name}`).classList.add('active');

  const titles = {
    dashboard: 'Dashboard',
    videos:    'Vídeos Gerados',
    search:    'Pesquisa',
    schedule:  'Agendamento de Postagem',
  };
  $('#page-title').textContent = titles[name] || name;

  if (name === 'dashboard') loadDashboard();
  if (name === 'videos')    loadVideos(1);
}

$$('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

// ── API helpers ───────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const res  = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Erro na API');
  return data;
}

// ── Badge HTML ────────────────────────────────────────────────────────
function badgeHTML(status) {
  const map = {
    concluido: ['badge-concluido', 'Concluído'],
    pendente:  ['badge-pendente',  'Pendente'],
    erro:      ['badge-erro',      'Erro'],
  };
  const [cls, label] = map[status] || ['badge-pendente', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ── Format date ───────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

// ════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ════════════════════════════════════════════════════════════════════════
async function loadDashboard() {
  try {
    const stats = await api('/api/stats');

    // Status badge
    $('#status-text').textContent = `${stats.total || 0} hinos registrados`;

    // Stat cards
    $('#stat-total').textContent    = stats.total     ?? 0;
    $('#stat-concluido').textContent = stats.concluido ?? 0;
    $('#stat-pendente').textContent  = stats.pendente  ?? 0;
    $('#stat-erro').textContent      = stats.erro      ?? 0;

    // Progress
    const pct = stats.total ? Math.round((stats.concluido / stats.total) * 100) : 0;
    $('#progress-bar').style.width    = `${pct}%`;
    $('#progress-label').textContent  = `${stats.concluido ?? 0} de ${stats.total ?? 0} — ${pct}%`;

    // Recent videos
    const recent = await api('/api/videos?page=1&per_page=8');
    const list   = $('#recent-list');
    if (!recent.videos.length) {
      list.innerHTML = '<div class="loader-inline">Nenhum vídeo gerado ainda.</div>';
      return;
    }

    list.innerHTML = recent.videos.map(v => `
      <div class="recent-item" data-num="${v.numero}" role="button" tabindex="0">
        <span class="recent-num">${String(v.numero).padStart(3, '0')}</span>
        <span class="recent-name">${escHTML(v.titulo)}</span>
        <span class="recent-file">${escHTML(v.video_file)}</span>
      </div>
    `).join('');

    $$('.recent-item', list).forEach(el => {
      el.addEventListener('click', () => openModal(Number(el.dataset.num)));
      el.addEventListener('keydown', e => e.key === 'Enter' && openModal(Number(el.dataset.num)));
    });

  } catch (err) {
    toast('Erro ao carregar dashboard: ' + err.message, 'error');
  }
}

// ════════════════════════════════════════════════════════════════════════
// VIDEOS LIST
// ════════════════════════════════════════════════════════════════════════
async function loadVideos(page = 1) {
  state.videosPage = page;
  const grid = $('#videos-grid');
  grid.innerHTML = '<div class="loader-inline">Carregando…</div>';

  try {
    const data = await api(`/api/videos?page=${page}&per_page=${state.perPage}`);
    state.videosTotal = data.total;
    state.videosPages = data.pages;

    $('#videos-count').textContent = `${data.total} vídeos gerados`;
    renderPagination('#pagination-top', page, data.pages);
    renderPagination('#pagination-bottom', page, data.pages);

    if (!data.videos.length) {
      grid.innerHTML = '<div class="loader-inline">Nenhum vídeo encontrado.</div>';
      return;
    }

    grid.innerHTML = data.videos.map(v => `
      <div class="video-card" data-num="${v.numero}" role="button" tabindex="0">
        <div class="vc-number">Hino ${String(v.numero).padStart(3, '0')}</div>
        <div class="vc-title">${escHTML(v.titulo)}</div>
        <div class="vc-file">📁 ${escHTML(v.video_file || '—')}</div>
        ${v.data_postagem
          ? `<div class="vc-date">📅 ${fmtDate(v.data_postagem)}</div>`
          : ''}
      </div>
    `).join('');

    $$('.video-card', grid).forEach(el => {
      el.addEventListener('click', () => openModal(Number(el.dataset.num)));
      el.addEventListener('keydown', e => e.key === 'Enter' && openModal(Number(el.dataset.num)));
    });

  } catch (err) {
    grid.innerHTML = `<div class="loader-inline">${escHTML(err.message)}</div>`;
    toast('Erro ao carregar vídeos.', 'error');
  }
}

function renderPagination(selector, current, pages) {
  const el = $(selector);
  if (!el) return;
  if (pages <= 1) { el.innerHTML = ''; return; }

  const range = [];
  for (let i = Math.max(1, current - 2); i <= Math.min(pages, current + 2); i++) range.push(i);

  el.innerHTML = [
    current > 1 ? `<button class="page-btn" data-p="${current-1}">‹</button>` : '',
    ...range.map(p => `<button class="page-btn ${p === current ? 'active' : ''}" data-p="${p}">${p}</button>`),
    current < pages ? `<button class="page-btn" data-p="${current+1}">›</button>` : '',
  ].join('');

  $$('.page-btn', el).forEach(btn => {
    btn.addEventListener('click', () => loadVideos(Number(btn.dataset.p)));
  });
}

// ════════════════════════════════════════════════════════════════════════
// SEARCH
// ════════════════════════════════════════════════════════════════════════
$('#search-btn').addEventListener('click', runSearch);
$('#search-input').addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });

async function runSearch() {
  const q    = $('#search-input').value.trim();
  const res  = $('#search-results');
  const panel= $('#detail-panel');

  if (!q) { res.innerHTML = ''; panel.style.display = 'none'; return; }

  res.innerHTML = '<div class="loader-inline">Pesquisando…</div>';
  panel.style.display = 'none';

  try {
    const data = await api(`/api/videos/search?q=${encodeURIComponent(q)}`);

    if (!data.videos.length) {
      res.innerHTML = '<div class="loader-inline">Nenhum resultado encontrado.</div>';
      return;
    }

    res.innerHTML = data.videos.map(v => `
      <div class="search-item" data-num="${v.numero}" role="button" tabindex="0">
        <span class="recent-num">${String(v.numero).padStart(3,'0')}</span>
        <span class="recent-name">${escHTML(v.titulo)}</span>
        <span class="recent-file">${escHTML(v.video_file || v.mp3_file)}</span>
        ${badgeHTML(v.status)}
      </div>
    `).join('');

    $$('.search-item', res).forEach(el => {
      el.addEventListener('click', () => showDetail(Number(el.dataset.num)));
      el.addEventListener('keydown', e => e.key === 'Enter' && showDetail(Number(el.dataset.num)));
    });

  } catch (err) {
    res.innerHTML = `<div class="loader-inline">${escHTML(err.message)}</div>`;
  }
}

async function showDetail(numero) {
  const panel = $('#detail-panel');
  const form  = $('#detail-form');
  const title = $('#detail-title');
  const badge = $('#detail-status-badge');

  panel.style.display = 'block';
  form.innerHTML = '<div class="loader-inline">Carregando…</div>';
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const v = await api(`/api/videos/${numero}`);

    title.textContent = `Hino ${String(v.numero).padStart(3,'0')}`;
    badge.outerHTML   = badgeHTML(v.status); // replace

    form.innerHTML = detailFormHTML(v);

  } catch (err) {
    form.innerHTML = `<div class="loader-inline">${escHTML(err.message)}</div>`;
  }
}

// ════════════════════════════════════════════════════════════════════════
// DETAIL FORM (shared between search panel and modal)
// ════════════════════════════════════════════════════════════════════════
function detailFormHTML(v) {
  return `
    <div class="field-group">
      <span class="field-label">Título para o YouTube</span>
      <input class="field-input" readonly value="${escAttr(v.titulo)}" />
    </div>
    <div class="field-group">
      <span class="field-label">Data de Postagem</span>
      <input class="field-input mono" readonly value="${v.data_postagem ? fmtDate(v.data_postagem) : '—'}" />
    </div>
    <div class="field-group full">
      <span class="field-label">Descrição para o YouTube</span>
      <textarea class="field-input" readonly rows="6">${escHTML(v.descricao)}</textarea>
    </div>
    <div class="field-group full">
      <span class="field-label">Tags para o YouTube</span>
      <textarea class="field-input" readonly rows="3">${escHTML(v.tags)}</textarea>
    </div>
    <div class="field-group">
      <span class="field-label">Arquivo de Vídeo</span>
      <input class="field-input mono" readonly value="${escAttr(v.video_file || '—')}" />
    </div>
    <div class="field-group">
      <span class="field-label">Arquivo de Thumb (imagem)</span>
      <input class="field-input mono" readonly value="${escAttr(v.thumb_file || '—')}" />
    </div>
    <div class="field-group">
      <span class="field-label">Hinário</span>
      <input class="field-input" readonly value="${escAttr(v.hinario)}" />
    </div>
    <div class="field-group">
      <span class="field-label">Status</span>
      <input class="field-input" readonly value="${escAttr(v.status)}" />
    </div>
    <div class="field-group">
      <span class="field-label">Arquivo de MP3</span>
      <input class="field-input mono" readonly value="${escAttr(v.mp3_file || '—')}" />
    </div>
    <div class="field-group">
      <span class="field-label">Atualizado em</span>
      <input class="field-input" readonly value="${escAttr(fmtDate(v.atualizado_em))}" />
    </div>
  `;
}

// ════════════════════════════════════════════════════════════════════════
// MODAL (from Videos grid)
// ════════════════════════════════════════════════════════════════════════
async function openModal(numero) {
  const backdrop = $('#modal-backdrop');
  const body     = $('#modal-body');

  backdrop.style.display = 'flex';
  body.innerHTML = '<div class="loader-inline">Carregando…</div>';

  try {
    const v = await api(`/api/videos/${numero}`);

    body.innerHTML = `
      <h2 class="modal-title">
        ${badgeHTML(v.status)}
        &nbsp;Hino ${String(v.numero).padStart(3,'0')} — ${escHTML(v.titulo)}
      </h2>
      <div class="modal-form">${detailFormHTML(v)}</div>
    `;

  } catch (err) {
    body.innerHTML = `<div class="loader-inline">${escHTML(err.message)}</div>`;
  }
}

$('#modal-close').addEventListener('click', () => {
  $('#modal-backdrop').style.display = 'none';
});

$('#modal-backdrop').addEventListener('click', e => {
  if (e.target === $('#modal-backdrop')) $('#modal-backdrop').style.display = 'none';
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('#modal-backdrop').style.display = 'none';
});

// ════════════════════════════════════════════════════════════════════════
// SCHEDULE
// ════════════════════════════════════════════════════════════════════════
$('#sch-preview-btn').addEventListener('click', previewSchedule);
$('#sch-apply-btn').addEventListener('click', applySchedule);

function getScheduleParams() {
  return {
    data_base:      $('#sch-data-base').value,
    intervalo_dias: parseInt($('#sch-intervalo').value) || 1,
    hora:           $('#sch-hora').value || '15:00',
  };
}

function previewSchedule() {
  const p = getScheduleParams();
  if (!p.data_base) { toast('Informe a data de início.', 'error'); return; }

  // Local preview: build dates without calling the API
  const tableCard = $('#sch-table-card');
  const tbody     = $('#sch-tbody');
  const banner    = $('#sch-preview');

  // Fetch the concluded videos to build preview
  api(`/api/videos?page=1&per_page=500`)
    .then(data => {
      const vids = data.videos;

      const rows = vids.map((v, i) => {
        const dt  = new Date(p.data_base + 'T' + p.hora);
        dt.setDate(dt.getDate() + i * p.intervalo_dias);
        const iso = dt.toISOString().slice(0, 16).replace('T', ' ');
        return { numero: v.numero, file: v.video_file, date: iso };
      });

      state.schedulePreview = rows;

      banner.style.display = 'block';
      banner.textContent = `${rows.length} vídeos serão agendados — primeiro: ${rows[0]?.date || '—'} · último: ${rows[rows.length-1]?.date || '—'}`;

      tableCard.style.display = 'block';
      tbody.innerHTML = rows.map(r => `
        <tr>
          <td class="mono-cell">${String(r.numero).padStart(3,'0')}</td>
          <td>${escHTML(r.file)}</td>
          <td class="date-cell">${r.date}</td>
        </tr>
      `).join('');
    })
    .catch(err => toast('Erro ao pré-visualizar: ' + err.message, 'error'));
}

async function applySchedule() {
  const p = getScheduleParams();
  if (!p.data_base) { toast('Informe a data de início.', 'error'); return; }

  $('#sch-apply-btn').disabled = true;
  $('#sch-apply-btn').textContent = 'Aplicando…';

  try {
    const result = await api('/api/schedule', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(p),
    });

    toast(`✅ ${result.atualizados} datas aplicadas com sucesso!`, 'success', 4000);
    previewSchedule(); // refresh table
  } catch (err) {
    toast('Erro: ' + err.message, 'error');
  } finally {
    $('#sch-apply-btn').disabled = false;
    $('#sch-apply-btn').textContent = 'Aplicar Datas';
  }
}

// ── Escape helpers ────────────────────────────────────────────────────
function escHTML(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(s) { return escHTML(s); }

// ── Init ──────────────────────────────────────────────────────────────
(function init() {
  // Set today as default schedule date
  const today = new Date().toISOString().slice(0, 10);
  $('#sch-data-base').value = today;

  switchView('dashboard');
})();
