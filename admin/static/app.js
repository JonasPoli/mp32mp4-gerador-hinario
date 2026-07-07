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
    'project-config': 'Configurações do Projeto',
  };
  $('#page-title').textContent = titles[name] || name;

  if (name === 'dashboard') loadDashboard();
  if (name === 'videos')    loadVideos(1);
  if (name === 'project-config') loadProjectConfig();
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
      if (state.currentView === 'project-config') loadProjectConfig();
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

  // Load resources for configuration dropdowns
  try {
    const res = await fetch('/api/resources');
    const resources = await res.json();
    
    // CSV options
    $('#cfg-csv-path').innerHTML = resources.csvs.map(path => 
      `<option value="${path}">${path}</option>`
    ).join('');

    // Pipeline options
    $('#cfg-pipeline').innerHTML = resources.pipelines.map(pip => 
      `<option value="${pip}">${pip}</option>`
    ).join('');

    // Vinheta options
    $('#cfg-vinheta').innerHTML = [
      '<option value="">Nenhuma</option>',
      ...resources.vinhetas.map(path => `<option value="${path}">${path}</option>`)
    ].join('');

    // Instrument options
    $('#cfg-instrumento').innerHTML = [
      '<option value="">Nenhum ícone</option>',
      ...resources.instrumentos.map(path => `<option value="${path}">${path}</option>`)
    ].join('');

  } catch (err) {
    console.error('Erro ao carregar recursos do servidor:', err);
  }

  // Set up project config form submission
  const configForm = $('#project-config-form');
  if (configForm) {
    configForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!state.activeProject) {
        toast('Nenhum projeto ativo selecionado.', 'error');
        return;
      }
      
      const submitBtn = $('#cfg-submit-btn');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Salvando...';

      const payload = {
        nome_exibicao: $('#cfg-nome').value.trim(),
        csv_path: $('#cfg-csv-path').value,
        inputs_dir: $('#cfg-inputs-dir').value.trim(),
        thumb_pipeline: $('#cfg-pipeline').value,
        vinheta: $('#cfg-vinheta').value,
        instrumento: $('#cfg-instrumento').value,
        titulo_template: $('#cfg-titulo').value.trim(),
        palavras_chaves: $('#cfg-palavras-chaves').value.trim(),
        descricao: $('#cfg-descricao').value.trim(),
        desenho: {
          numero: {
            x: parseInt($('#cfg-num-x').value) || 0,
            y_top: parseInt($('#cfg-num-ytop').value) || 0,
            y_bottom: parseInt($('#cfg-num-ybottom').value) || 0,
            max_width: parseInt($('#cfg-num-maxw').value) || 0,
            cor: toRgbaArray($('#cfg-num-color').value, $('#cfg-num-alpha').value),
            brilho: {
              raio: parseInt($('#cfg-num-glow-r').value) || 0,
              cor: toRgbaArray($('#cfg-num-glow-color').value, $('#cfg-num-glow-alpha').value)
            }
          },
          nome: {
            x: parseInt($('#cfg-name-x').value) || 0,
            y_top: parseInt($('#cfg-name-ytop').value) || 0,
            y_bottom: parseInt($('#cfg-name-ybottom').value) || 0,
            max_width: parseInt($('#cfg-name-maxw').value) || 0,
            max_font_size: parseInt($('#cfg-name-size').value) || 0,
            align: $('#cfg-name-align').value,
            cor: toRgbaArray($('#cfg-name-color').value, $('#cfg-name-alpha').value),
            brilho: {
              raio: parseInt($('#cfg-name-glow-r').value) || 0,
              cor: toRgbaArray($('#cfg-name-glow-color').value, $('#cfg-name-glow-alpha').value)
            }
          }
        }
      };

      try {
        const res = await fetch(`/api/projects/${state.activeProject}/update`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });
        
        const result = await res.json();
        if (!res.ok) {
          throw new Error(result.error || 'Erro ao salvar configurações');
        }
        
        toast('Configurações salvas com sucesso!', 'success');
        await reloadProjects(state.activeProject, false);
      } catch (err) {
        toast('Erro: ' + err.message, 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '💾 Salvar Configurações';
      }
    });
  }

  // Coordinate & style change triggers (to update Canvas in real-time)
  $$('.layout-trigger').forEach(el => {
    el.addEventListener('input', () => {
      // Update alpha labels if it's an alpha slider
      if (el.classList.contains('alpha-slider')) {
        const valLabel = $(`#${el.id}-val`);
        if (valLabel) valLabel.textContent = el.value;
      }
      drawLayoutOnCanvas();
    });
  });

  // Set up thumbnail test button
  const testThumbBtn = $('#cfg-test-thumb-btn');
  if (testThumbBtn) {
    testThumbBtn.addEventListener('click', async () => {
      if (!state.activeProject) {
        toast('Nenhum projeto ativo selecionado.', 'error');
        return;
      }
      const testNum = $('#cfg-test-num').value;
      if (!testNum) {
        toast('Informe o número do hino de teste.', 'error');
        return;
      }
      
      testThumbBtn.disabled = true;
      testThumbBtn.textContent = 'Gerando...';
      $('#test-result-wrapper').style.display = 'none';

      try {
        toast(`Solicitando geração de thumbnail de teste para o hino ${testNum}...`, 'info');
        const res = await fetch(`/api/videos/${state.activeProject}/${testNum}/gerar-thumb`, {
          method: 'POST'
        });
        const result = await res.json();
        if (!res.ok) {
          throw new Error(result.error || 'Erro ao gerar miniatura');
        }

        toast('Thumbnail de teste gerada com sucesso!', 'success');
        $('#test-result-img').src = `${result.thumb_url}?t=${Date.now()}`;
        $('#test-result-wrapper').style.display = 'block';
      } catch (err) {
        toast('Erro no teste: ' + err.message, 'error');
      } finally {
        testThumbBtn.disabled = false;
        testThumbBtn.textContent = '🖼️ Gerar Teste de Thumb';
      }
    });
  }

  switchView('dashboard');
}

// ── Color helpers ─────────────────────────────────────────────────────
function parseRgbaArray(arr) {
  if (!arr || arr.length < 3) return { hex: '#ffffff', alpha: 255 };
  const r = arr[0].toString(16).padStart(2, '0');
  const g = arr[1].toString(16).padStart(2, '0');
  const b = arr[2].toString(16).padStart(2, '0');
  const hex = `#${r}${g}${b}`;
  const alpha = arr.length > 3 ? arr[3] : 255;
  return { hex, alpha };
}

function toRgbaArray(hex, alpha) {
  hex = hex.replace('#', '');
  if (hex.length === 3) {
    hex = hex.split('').map(c => c + c).join('');
  }
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return [r, g, b, parseInt(alpha) ?? 255];
}

// ── Canvas Renderer ───────────────────────────────────────────────────
let mascaraImageCache = {};

function drawLayoutOnCanvas() {
  const canvas = $('#layout-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const project = state.activeProject;
  if (!project) return;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const drawBoxes = () => {
    // Read input coordinates (with fallbacks)
    const numX = (parseInt($('#cfg-num-x').value) || 0) / 3;
    const numYtop = (parseInt($('#cfg-num-ytop').value) || 0) / 3;
    const numYbottom = (parseInt($('#cfg-num-ybottom').value) || 0) / 3;
    const numMaxw = (parseInt($('#cfg-num-maxw').value) || 0) / 3;

    const nameX = (parseInt($('#cfg-name-x').value) || 0) / 3;
    const nameYtop = (parseInt($('#cfg-name-ytop').value) || 0) / 3;
    const nameYbottom = (parseInt($('#cfg-name-ybottom').value) || 0) / 3;
    const nameMaxw = (parseInt($('#cfg-name-maxw').value) || 0) / 3;

    // Draw Number Area
    ctx.fillStyle = 'rgba(34, 197, 94, 0.2)';
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 1.5;
    ctx.fillRect(numX, numYtop, numMaxw, numYbottom - numYtop);
    ctx.strokeRect(numX, numYtop, numMaxw, numYbottom - numYtop);

    // Draw Name Area
    ctx.fillStyle = 'rgba(124, 92, 252, 0.2)';
    ctx.strokeStyle = '#7c5cfc';
    ctx.fillRect(nameX, nameYtop, nameMaxw, nameYbottom - nameYtop);
    ctx.strokeRect(nameX, nameYtop, nameMaxw, nameYbottom - nameYtop);
  };

  const imgUrl = `/api/projects/${project}/mascara?t=${Date.now()}`;
  
  if (mascaraImageCache[project]) {
    const img = mascaraImageCache[project];
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    drawBoxes();
  } else {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = imgUrl;
    img.onload = () => {
      mascaraImageCache[project] = img;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      drawBoxes();
    };
    img.onerror = () => {
      ctx.fillStyle = '#10121f';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#6b6a8a';
      ctx.font = '12px sans-serif';
      ctx.fillText('Nenhuma máscara de fundo carregada', 20, 40);
      drawBoxes();
    };
  }
}

function loadProjectConfig() {
  if (!state.activeProject) {
    toast('Nenhum projeto ativo selecionado.', 'error');
    return;
  }
  const cfg = state.projects[state.activeProject];
  if (!cfg) return;

  // General fields
  $('#cfg-nome').value = cfg.nome_exibicao || '';
  $('#cfg-csv-path').value = cfg.csv_path || '';
  $('#cfg-inputs-dir').value = cfg.inputs_dir || cfg.mp3_dir || '';
  $('#cfg-pipeline').value = cfg.thumb_pipeline || 'v01';
  $('#cfg-vinheta').value = cfg.vinheta || '';
  $('#cfg-instrumento').value = cfg.instrumento || '';

  // YouTube Templates
  $('#cfg-titulo').value = cfg.titulo_template || '';
  $('#cfg-palavras-chaves').value = cfg.palavras_chaves || '';
  $('#cfg-descricao').value = cfg.descricao || '';

  // Desenho defaults
  const d = cfg.desenho || {};
  const num = d.numero || { x: 120, y_top: 150, y_bottom: 780, max_width: 580, cor: [26, 45, 90, 255] };
  const name = d.nome || { x: 780, y_top: 200, y_bottom: 800, max_width: 550, max_font_size: 100, align: 'left', cor: [26, 45, 90, 255] };

  // Numero Coords
  $('#cfg-num-x').value = num.x ?? 120;
  $('#cfg-num-ytop').value = num.y_top ?? 150;
  $('#cfg-num-ybottom').value = num.y_bottom ?? 780;
  $('#cfg-num-maxw').value = num.max_width ?? 580;

  // Numero Colors
  const numCor = parseRgbaArray(num.cor);
  $('#cfg-num-color').value = numCor.hex;
  $('#cfg-num-alpha').value = numCor.alpha;
  $('#cfg-num-alpha-val').textContent = numCor.alpha;

  // Numero Glow
  const numGlow = num.brilho || { raio: 3, cor: [255, 255, 255, 255] };
  $('#cfg-num-glow-r').value = numGlow.raio ?? 3;
  const numGlowCor = parseRgbaArray(numGlow.cor);
  $('#cfg-num-glow-color').value = numGlowCor.hex;
  $('#cfg-num-glow-alpha').value = numGlowCor.alpha;
  $('#cfg-num-glow-alpha-val').textContent = numGlowCor.alpha;

  // Nome Coords
  $('#cfg-name-x').value = name.x ?? 780;
  $('#cfg-name-ytop').value = name.y_top ?? 200;
  $('#cfg-name-ybottom').value = name.y_bottom ?? 800;
  $('#cfg-name-maxw').value = name.max_width ?? 550;
  $('#cfg-name-size').value = name.max_font_size ?? 100;
  $('#cfg-name-align').value = name.align || 'left';

  // Nome Colors
  const nameCor = parseRgbaArray(name.cor);
  $('#cfg-name-color').value = nameCor.hex;
  $('#cfg-name-alpha').value = nameCor.alpha;
  $('#cfg-name-alpha-val').textContent = nameCor.alpha;

  // Nome Glow
  const nameGlow = name.brilho || { raio: 3, cor: [255, 255, 255, 255] };
  $('#cfg-name-glow-r').value = nameGlow.raio ?? 3;
  const nameGlowCor = parseRgbaArray(nameGlow.cor);
  $('#cfg-name-glow-color').value = nameGlowCor.hex;
  $('#cfg-name-glow-alpha').value = nameGlowCor.alpha;
  $('#cfg-name-glow-alpha-val').textContent = nameGlowCor.alpha;

  // Clear test result preview
  $('#test-result-wrapper').style.display = 'none';
  $('#test-result-img').removeAttribute('src');

  // Redraw Canvas
  // Remove project cache to reload mask dynamically if it changed
  delete mascaraImageCache[state.activeProject];
  drawLayoutOnCanvas();
}

async function reloadProjects(selectKey = null, changeView = true) {
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
    if (changeView) {
      switchView('dashboard');
    }
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

