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
  activeProject: '',
  projects: {},
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
    'new-project': 'Cadastrar Novo Projeto',
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
  let url = path;
  if (state.activeProject) {
    const separator = path.includes('?') ? '&' : '?';
    url = `${path}${separator}projeto=${state.activeProject}`;
  }
  const res  = await fetch(url, opts);
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
  const thumbUrl = v.thumb_exists 
    ? `/thumbs/${v.thumb_file}?t=${Date.now()}` 
    : '';

  return `
    <div class="field-group full" style="display: flex; flex-direction: column; gap: 0.5rem; align-items: center; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem;">
      <span class="field-label" style="align-self: flex-start;">Visualização da Miniatura (Thumbnail)</span>
      <div class="thumb-preview-container" style="width: 100%; max-width: 480px; aspect-ratio: 16/9; background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative;">
        ${thumbUrl 
          ? `<img src="${thumbUrl}" id="thumb-preview-img-${v.numero}" style="width: 100%; height: 100%; object-fit: contain;" />` 
          : `<span id="thumb-preview-placeholder-${v.numero}" style="color: var(--text-3); font-size: 0.9rem;">Imagem não gerada</span>`
        }
      </div>
      <button type="button" class="btn-secondary" onclick="gerarThumbHino('${v.projeto}', ${v.numero})" style="margin-top: 0.5rem; padding: 0.5rem 1rem; font-size: 0.85rem; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
        🖼️ Gerar Apenas Imagem/Thumb
      </button>
    </div>

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

// Toggle coletâneas options
const schColCheck = $('#sch-incluir-coletaneas');
if (schColCheck) {
  schColCheck.addEventListener('change', () => {
    const opts = $('#sch-coletaneas-options');
    if (opts) opts.style.display = schColCheck.checked ? 'block' : 'none';
  });
}

function getScheduleParams() {
  return {
    projeto:               state.activeProject,
    data_base:             $('#sch-data-base').value,
    intervalo_dias:        parseInt($('#sch-intervalo').value) || 1,
    hora:                  $('#sch-hora').value || '15:00',
    incluir_coletaneas:    $('#sch-incluir-coletaneas')?.checked || false,
    intervalo_coletaneas:  parseInt($('#sch-intervalo-coletaneas')?.value) || 7,
  };
}

function previewSchedule() {
  const p = getScheduleParams();
  if (!p.data_base) { toast('Informe a data de início.', 'error'); return; }

  // Local preview: build dates without calling the API
  const tableCard    = $('#sch-table-card');
  const tbody        = $('#sch-tbody');
  const banner       = $('#sch-preview');
  const colTableCard = $('#sch-col-table-card');
  const colTbody     = $('#sch-col-tbody');

  // Fetch the concluded videos to build preview
  api(`/api/videos?page=1&per_page=500`)
    .then(async data => {
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

      // Coletâneas preview
      if (p.incluir_coletaneas) {
        try {
          const coletaneas = await fetch('/api/coletaneas').then(r => r.json());
          const colRows = coletaneas
            .filter(c => c.video_file)
            .map((c, j) => {
              const baseOffset = rows.length * p.intervalo_dias;
              const dt = new Date(p.data_base + 'T' + p.hora);
              dt.setDate(dt.getDate() + baseOffset + j * p.intervalo_coletaneas);
              const iso = dt.toISOString().slice(0, 16).replace('T', ' ');
              return { titulo: c.titulo, file: c.video_file, date: iso };
            });

          colTableCard.style.display = colRows.length > 0 ? 'block' : 'none';
          colTbody.innerHTML = colRows.map(r => `
            <tr>
              <td>${escHTML(r.titulo)}</td>
              <td>${escHTML(r.file)}</td>
              <td class="date-cell">${r.date}</td>
            </tr>
          `).join('');

          if (colRows.length > 0) {
            banner.textContent += ` | ${colRows.length} coletâneas — primeira: ${colRows[0]?.date || '—'}`;
          }
        } catch (err) {
          toast('Aviso: erro ao carregar coletâneas: ' + err.message, 'error');
        }
      } else {
        colTableCard.style.display = 'none';
      }
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

    let msg = `✅ ${result.atualizados} datas aplicadas com sucesso!`;
    if (result.coletaneas && result.coletaneas.length > 0) {
      msg += ` | ${result.coletaneas.length} coletâneas incluídas na visualização.`;
      // Exibir tabela de coletâneas com as datas retornadas pela API
      const colTableCard = $('#sch-col-table-card');
      const colTbody     = $('#sch-col-tbody');
      colTableCard.style.display = 'block';
      colTbody.innerHTML = result.coletaneas.map(c => {
        const dataPart = c.data_postagem.replace('T', ' ').slice(0, 16);
        return `
          <tr>
            <td>${escHTML(c.titulo)}</td>
            <td>${escHTML(c.video_file)}</td>
            <td class="date-cell">${dataPart}</td>
          </tr>
        `;
      }).join('');
    }
    toast(msg, 'success', 5000);
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
async function init() {
  // Set today as default schedule date
  const today = new Date().toISOString().slice(0, 10);
  $('#sch-data-base').value = today;

  try {
    const res = await fetch('/api/projects');
    const projects = await res.json();
    state.projects = projects;
    
    const selector = $('#project-select');
    selector.innerHTML = Object.entries(projects).map(([key, cfg]) => 
      `<option value="${key}">${escHTML(cfg.nome_exibicao || key)}</option>`
    ).join('');
    
    state.activeProject = selector.value;
    
    selector.addEventListener('change', (e) => {
      state.activeProject = e.target.value;
      if (state.currentView === 'dashboard') loadDashboard();
      if (state.currentView === 'videos') loadVideos(1);
      if (state.currentView === 'search') runSearch();
    });
    
    const csvBtn = $('#download-csv-btn');
    if (csvBtn) {
      csvBtn.addEventListener('click', () => {
        if (!state.activeProject) {
          toast('Nenhum projeto ativo selecionado.', 'error');
          return;
        }
        window.open(`/api/projects/${state.activeProject}/export-csv`, '_blank');
      });
    }

    const colCsvBtn = $('#download-coletaneas-csv-btn');
    if (colCsvBtn) {
      colCsvBtn.addEventListener('click', () => {
        window.open('/api/coletaneas/export-csv', '_blank');
      });
    }
    
    switchView('dashboard');
  } catch (err) {
    toast('Erro ao carregar projetos: ' + err.message, 'error');
    switchView('dashboard');
  }
  // Set up auto-slugification for new project form
  const nameInput = $('#proj-nome');
  const idInput = $('#proj-id');
  if (nameInput && idInput) {
    nameInput.addEventListener('input', () => {
      if (!idInput.dataset.manual) {
        idInput.value = nameInput.value
          .toLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '') // Remove accents
          .replace(/[^a-z0-9_]/g, '_')     // Replace non-alphanumeric with underline
          .replace(/_+/g, '_')              // Collapse multiple underlines
          .replace(/^_+|_+$/g, '');         // Trim underlines
      }
    });
    idInput.addEventListener('input', () => {
      idInput.dataset.manual = 'true';
    });
  }

  // Set up project creation form submission
  const form = $('#new-project-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const submitBtn = $('#proj-submit-btn');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Criando...';
      
      const formData = new FormData(form);
      try {
        const res = await fetch('/api/projects/create', {
          method: 'POST',
          body: formData
        });
        
        const result = await res.json();
        if (!res.ok) {
          throw new Error(result.error || 'Erro ao criar o projeto');
        }
        
        toast('Projeto criado com sucesso!', 'success');
        form.reset();
        if (idInput) delete idInput.dataset.manual;
        
        // Reload projects and select the new one
        await reloadProjects(result.projeto_key);
        
      } catch (err) {
        toast('Erro: ' + err.message, 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Cadastrar Projeto';
      }
    });
  }

  switchView('dashboard');
}

async function reloadProjects(selectKey = null) {
  try {
    const res = await fetch('/api/projects');
    const projects = await res.json();
    state.projects = projects;
    
    const selector = $('#project-select');
    selector.innerHTML = Object.entries(projects).map(([key, cfg]) => 
      `<option value="${key}">${escHTML(cfg.nome_exibicao || key)}</option>`
    ).join('');
    
    if (selectKey && projects[selectKey]) {
      selector.value = selectKey;
    }
    
    state.activeProject = selector.value;
    switchView('dashboard');
  } catch (err) {
    toast('Erro ao atualizar lista de projetos: ' + err.message, 'error');
  }
}

async function gerarThumbHino(projeto, numero) {
  try {
    toast(`Gerando imagem do hino ${numero}...`, 'info');
    
    const res = await fetch(`/api/videos/${projeto}/${numero}/gerar-thumb`, {
      method: 'POST'
    });
    
    const result = await res.json();
    if (!res.ok) {
      throw new Error(result.error || 'Erro ao gerar imagem');
    }
    
    toast('Imagem gerada com sucesso!', 'success');
    
    // Update the image preview in the UI
    const img = $(`#thumb-preview-img-${numero}`);
    const placeholder = $(`#thumb-preview-placeholder-${numero}`);
    const newSrc = `${result.thumb_url}?t=${Date.now()}`;
    
    if (img) {
      img.src = newSrc;
    } else if (placeholder) {
      const container = placeholder.parentElement;
      container.innerHTML = `<img src="${newSrc}" id="thumb-preview-img-${numero}" style="width: 100%; height: 100%; object-fit: contain;" />`;
    }
    
  } catch (err) {
    toast('Erro: ' + err.message, 'error');
  }
}

init();
