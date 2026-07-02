/**
 * app.js — Dashboard Sitrad Coletor
 * Suporte a múltiplos modelos: TC-900E, PCT-122E Plus
 * Model ID 117 = PCT-122E Plus; outros = TC-900E (layout básico)
 */

const POLL_INTERVAL_MS = 3000;
const HISTORY_LIMIT    = 120;    // 120 × 30s = 1h de histórico

// PCT-122E Plus model IDs (FullGauge)
const PCT122E_MODEL_IDS = new Set([117]);

// ── Configuração de áreas de monitoramento ─────────────────────
// Chave: trecho do nome do instrumento (case-insensitive)
// Valor: nome da área exibida no overview
const AREA_CONFIG = [
  { match: ['TC-900', 'TC900', 'Log'],        area: 'ABOVE ADIUM' },
  { match: ['PCT-122', 'PCT122', 'Chiesi', 'Condensadora'], area: 'Chiesi' },
];
const AREA_DEFAULT = 'Geral';

function getArea(instrumentName) {
  const lower = instrumentName.toLowerCase();
  for (const cfg of AREA_CONFIG) {
    if (cfg.match.some(m => lower.includes(m.toLowerCase()))) return cfg.area;
  }
  return AREA_DEFAULT;
}

// ── Spotlight de alarmes ───────────────────────────────────────
let _spotlightItems = [];   // instrumentos com alarme ativo
let _spotlightIndex = 0;
let _spotlightTimer = null;

// ── Estado da aplicação ────────────────────────────────────────
let selectedInstrumentId = null;
let currentModelId       = null;
let mainChart            = null;
let pollTimer            = null;

// ── Referências DOM ────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── API ────────────────────────────────────────────────────────
const API = {
  async instruments()    { return _get('/api/v1/instruments'); },
  async state(id)        { return _get(`/api/v1/instruments/${id}/state`); },
  async history(id)      { return _get(`/api/v1/instruments/${id}/history?limit=${HISTORY_LIMIT}`); },
};

async function _get(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status} ${path}`);
  return r.json();
}

// ── Expõe funções chamadas por onclick= no HTML (módulos ES não são globais) ──
window.triggerAIFromAlarm = (...args) => triggerAIFromAlarm(...args);
window.openDemoPanel      = (...args) => openDemoPanel(...args);
window.closeDemoPanel     = (...args) => closeDemoPanel(...args);

// ── Sessão / Auth ──────────────────────────────────────────────
let _currentUser = null;   // { username, role }

async function initAuth() {
  try {
    const res = await fetch('/api/v1/me');
    if (res.status === 401) { window.location.replace('/login'); return false; }
    _currentUser = await res.json();
  } catch {
    window.location.replace('/login');
    return false;
  }

  // Mostra nome e perfil no header
  const badge = $('user-badge');
  if (badge) {
    const roleLabel = _currentUser.role === 'admin' ? 'Admin' : 'Visualização';
    badge.textContent = `${_currentUser.username}  ·  ${roleLabel}`;
    if (_currentUser.role !== 'admin') {
      badge.style.background = 'rgba(139,148,158,.12)';
      badge.style.color      = 'var(--muted)';
      badge.style.border     = '1px solid rgba(139,148,158,.2)';
    }
  }

  // Esconde recursos de admin para viewer
  if (_currentUser.role !== 'admin') {
    const fab  = $('demo-fab');
    const side = $('btn-normalize-sidebar');
    if (fab)  fab.style.display  = 'none';
    if (side) side.style.display = 'none';
  }

  return true;
}

async function doLogout() {
  await fetch('/logout', { method: 'POST' });
  window.location.replace('/login');
}
window.doLogout = doLogout;

// ── Inicialização ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const ok = await initAuth();
  if (!ok) return;

  await showOverview();                      // começa no overview
  setInterval(refreshOverview, 5_000);       // atualiza cards a cada 5s
  setInterval(loadInstruments, 15_000);      // atualiza sidebar a cada 15s
  startPoll();

  // Botão voltar para overview
  $('btn-back-overview').addEventListener('click', showOverview);
  // Botão fechar caixa IA inline
  $('inline-ai-box').querySelector('.inline-ai-close')
    .addEventListener('click', () => $('inline-ai-box').classList.add('hidden'));
});

// ══════════════════════════════════════════════════════════════
// OVERVIEW — TELA INICIAL
// ══════════════════════════════════════════════════════════════

async function showOverview() {
  // Mostra overview, oculta detalhe
  $('overview-screen').classList.remove('hidden');
  $('instrument-panel').classList.add('hidden');
  $('empty-state').classList.add('hidden');
  selectedInstrumentId = null;

  // Atualiza sidebar (nenhum selecionado)
  document.querySelectorAll('.instrument-item').forEach(li =>
    li.classList.remove('instrument-item--active'));

  await refreshOverview();
  await loadInstruments();
}

async function refreshOverview() {
  let data;
  try {
    data = await _get('/api/v1/overview');
    $('collector-dot').className     = 'dot dot--online';
    $('collector-label').textContent = 'Conectado';
  } catch {
    $('collector-dot').className     = 'dot dot--offline';
    $('collector-label').textContent = 'Sem conexão';
    return;
  }

  $('overview-last-update').textContent =
    'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');

  // Estatísticas globais
  const total   = data.length;
  const online  = data.filter(d => d.online).length;
  const offline = total - online;
  const alarmed = data.filter(d => d.alarm_count > 0).length;

  $('overview-subtitle').textContent =
    `${total} controlador${total !== 1 ? 'es' : ''} monitorado${total !== 1 ? 's' : ''}`;

  $('overview-stats').innerHTML = `
    <div class="ov-stat">
      <span class="ov-stat-dot ov-stat-dot--online"></span>
      <span>${online} online</span>
    </div>
    ${offline ? `<div class="ov-stat">
      <span class="ov-stat-dot ov-stat-dot--offline"></span>
      <span>${offline} offline</span>
    </div>` : ''}
    ${alarmed ? `<div class="ov-stat">
      <span class="ov-stat-dot ov-stat-dot--alarm"></span>
      <span>${alarmed} em alarme</span>
    </div>` : ''}
  `;

  if (!data.length) {
    $('overview-grid').innerHTML = '<div class="overview-loading"><span>Nenhum instrumento encontrado</span></div>';
    return;
  }

  // Agrupa por área
  const areaMap = new Map();
  for (const d of data) {
    const area = getArea(d.name);
    if (!areaMap.has(area)) areaMap.set(area, []);
    areaMap.get(area).push(d);
  }

  // Ordena instrumentos dentro de cada área: alarmados → offline → ok
  for (const items of areaMap.values()) {
    items.sort((a, b) => {
      const scoreA = (a.alarm_count > 0 ? 200 : 0) + (!a.online ? 100 : 0);
      const scoreB = (b.alarm_count > 0 ? 200 : 0) + (!b.online ? 100 : 0);
      return scoreB - scoreA || a.name.localeCompare(b.name);
    });
  }

  // Renderiza seções de área
  let html = '';
  for (const [area, items] of areaMap) {
    const hasAlarm   = items.some(d => d.alarm_count > 0);
    const hasOffline = items.some(d => !d.online);
    const areaState  = hasAlarm ? 'alarm' : hasOffline ? 'offline' : 'ok';
    html += `
      <div class="ov-area">
        <div class="ov-area-header ov-area-header--${areaState}">
          <span class="ov-area-dot ov-area-dot--${areaState}"></span>
          <span class="ov-area-name">${area}</span>
          <span class="ov-area-count">${items.length} equip.</span>
        </div>
        <div class="ov-area-cards">
          ${items.map(d => buildCard(d)).join('')}
        </div>
      </div>`;
  }
  $('overview-grid').innerHTML = html;

  // Evento de clique nos cards
  $('overview-grid').querySelectorAll('.ov-card').forEach(card => {
    card.addEventListener('click', () => {
      const id      = Number(card.dataset.id);
      const modelId = Number(card.dataset.modelId);
      openDetail(id, modelId);
    });
  });

  // Atualiza spotlight de alarmes
  updateSpotlight(data);

  // Atualiza log de ocorrências
  refreshAlarmLog();
}

function updateSpotlight(data) {
  const alarmed = data.filter(d => d.alarm_count > 0);

  // Para o timer atual para reiniciar limpo
  clearInterval(_spotlightTimer);
  _spotlightTimer = null;

  _spotlightItems = alarmed;
  _spotlightIndex = Math.min(_spotlightIndex, Math.max(alarmed.length - 1, 0));

  renderSpotlightSlide();

  if (alarmed.length > 1) {
    _spotlightTimer = setInterval(() => {
      _spotlightIndex = (_spotlightIndex + 1) % _spotlightItems.length;
      renderSpotlightSlide(true);
    }, 5000);
  }
}

function renderSpotlightSlide(animate = false) {
  const body = $('ov-spotlight-body');
  const nav  = $('ov-spotlight-nav');

  if (!_spotlightItems.length) {
    // Nenhum alarme ativo
    body.innerHTML = `
      <div class="ov-spotlight-ok">
        <div class="ov-spotlight-ok-icon">✅</div>
        <div class="ov-spotlight-ok-text">Instrumentos sem falha no sistema</div>
        <div class="ov-spotlight-ok-sub">Todos os controladores operando normalmente</div>
      </div>`;
    nav.innerHTML = '';
    return;
  }

  const d = _spotlightItems[_spotlightIndex];

  // Dots de navegação
  nav.innerHTML = _spotlightItems.map((_, i) =>
    `<span class="sp-dot${i === _spotlightIndex ? ' sp-dot--active' : ''}"></span>`
  ).join('');

  // Monta card completo
  const cardHtml = buildCard(d);

  if (animate) {
    // Fade out → troca → fade in
    const existing = body.querySelector('.ov-card');
    if (existing) {
      existing.classList.add('sp-fade');
      setTimeout(() => { body.innerHTML = cardHtml; attachSpotlightClick(body, d); }, 340);
    } else {
      body.innerHTML = cardHtml;
      attachSpotlightClick(body, d);
    }
  } else {
    body.innerHTML = cardHtml;
    attachSpotlightClick(body, d);
  }
}

function attachSpotlightClick(body, d) {
  const card = body.querySelector('.ov-card');
  if (card) {
    card.style.cursor = 'pointer';
    card.addEventListener('click', () => openDetail(d.id, d.model_id));
  }
}

async function refreshAlarmLog() {
  let log;
  try { log = await _get('/api/v1/alarm-log?limit=20'); }
  catch { return; }

  const body = $('ov-log-body');
  if (!log.length) {
    body.innerHTML = '<div class="ov-log-empty">Nenhuma ocorrência registrada.</div>';
    $('ov-log-status').textContent = '';
    return;
  }

  const activeCount = log.filter(e => e.is_active).length;
  $('ov-log-status').textContent = activeCount
    ? `${activeCount} ativo${activeCount > 1 ? 's' : ''}`
    : 'Tudo resolvido';
  $('ov-log-status').className = 'ov-log-status ' + (activeCount ? 'ov-log-status--active' : 'ov-log-status--ok');

  body.innerHTML = log.map(e => {
    const icon     = e.is_active
      ? (e.severity === 'alarm' ? '🔴' : '🟡')
      : '✓';
    const stateClass = e.is_active
      ? (e.severity === 'alarm' ? 'ov-log-row--alarm' : 'ov-log-row--warn')
      : 'ov-log-row--resolved';
    const timeStr  = fmtLogTime(e.started_at);
    const duration = e.cleared_at
      ? fmtDuration(e.started_at, e.cleared_at)
      : (e.is_active ? 'em andamento' : '');

    const assumedHtml = e.assumed_by
      ? `<span class="ov-log-assumed">👷 ${e.assumed_by}</span>`
      : (e.is_active ? `<span class="ov-log-unassumed">Aguardando</span>` : '');

    return `
      <div class="ov-log-row ${stateClass}">
        <span class="ov-log-icon">${icon}</span>
        <span class="ov-log-code">${e.code}</span>
        <span class="ov-log-instr">${e.instrument_name}</span>
        <span class="ov-log-desc">${e.description}</span>
        <span class="ov-log-time">${timeStr}</span>
        ${assumedHtml}
        <span class="ov-log-dur">${duration}</span>
      </div>`;
  }).join('');
}

function fmtLogTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
}

function fmtDuration(startIso, endIso) {
  const mins = Math.round((new Date(endIso) - new Date(startIso)) / 60000);
  if (mins < 1)  return '< 1min';
  if (mins < 60) return `${mins}min`;
  return `${Math.floor(mins/60)}h${mins%60 ? (mins%60)+'min' : ''}`;
}

function buildCard(d) {
  const isPCT   = d.model_id === 117;
  const s       = d.sensors || {};
  const out     = d.outputs || {};
  const isAlarm = d.alarm_count > 0 && d.active_alarms?.some(a => a.severity === 'alarm');
  const isWarn  = d.alarm_count > 0 && !isAlarm;

  const cardClass = d.alarm_count > 0
    ? (isAlarm ? 'ov-card ov-card--alarm' : 'ov-card ov-card--warn')
    : (!d.online ? 'ov-card ov-card--offline' : 'ov-card');

  // Badge do modelo
  const modelBadge = d.model_name
    ? `<span class="ov-model-badge">${d.model_name}</span>` : '';

  // Indicador de fonte (emulador)
  const sourceBadge = d.source === 'emulator'
    ? `<span style="font-size:9px;color:var(--cyan);margin-left:4px" title="Emulador">🔵</span>` : '';

  // Sensores chave
  let sensorsHtml = '';
  if (!d.has_data) {
    sensorsHtml = `<div style="color:var(--text-dim);font-size:12px;padding:8px 0">
      Aguardando primeira leitura...</div>`;
  } else if (isPCT) {
    sensorsHtml = `
      <div class="ov-sensors-grid">
        ${ovSensor('P1 Sucção', s.p1, 'PSIG', 'psi')}
        ${ovSensor('P2 Descarga', s.p2, 'PSIG', 'psi')}
        ${ovSensor('T3 Câmara', s.t3, '°C', tempColor(s.t3, -20, -14))}
        ${ovSensor('SH', s.superheat, 'K', shColor(s.superheat))}
      </div>`;
  } else {
    sensorsHtml = `
      <div class="ov-sensors-grid">
        ${ovSensor('T1 Sonda 1', s.t1, '°C', tempColor(s.t1, -25, -10))}
        ${ovSensor('T2 Sonda 2', s.t2, '°C', tempColor(s.t2, -25, -10))}
        ${ovSensor('T3 Sonda 3', s.t3, '°C', tempColor(s.t3, -22, -14))}
        ${ovSensor('Setpoint', s.setpoint, '°C', 'ok')}
      </div>`;
  }

  // Outputs
  const outItems = isPCT
    ? [['Comp.', out.refrigeration, 'green'], ['Vent.', out.fan, 'green'], ['Deg.', out.defrost, 'yellow']]
    : [['Comp.', out.refrigeration, 'green'], ['Vent.', out.fan, 'green'], ['Deg.', out.defrost, 'yellow']];
  const outputsHtml = `<div class="ov-outputs">
    ${outItems.map(([label, active, color]) =>
      `<div class="ov-output">
        <div class="ov-led ${active ? `ov-led--on-${color}` : ''}"></div>
        <span>${label}</span>
      </div>`
    ).join('')}
    ${d.process_text ? `<span class="badge badge--${processBadgeClass(d.process_text)}" style="font-size:9px;padding:1px 7px">${d.process_text}</span>` : ''}
  </div>`;

  // Footer — alarmes
  let footerHtml;
  if (!d.online) {
    const agMin = Math.round((d.age_s || 0) / 60);
    footerHtml = `
      <span style="font-size:11px;color:var(--red)">⚠ Offline há ${agMin} min</span>
      ${fixTimeHtml(d.avg_fix_min)}`;
  } else if (d.alarm_count === 0) {
    footerHtml = `
      <span class="ov-alarm-none">✓ Sem alarmes ativos</span>
      ${fixTimeHtml(d.avg_fix_min)}`;
  } else {
    const first = d.active_alarms[0];
    const icon  = isAlarm ? '🔴' : '🟡';
    const dur   = d.alarm_duration_min != null
      ? `há ${d.alarm_duration_min < 60
          ? d.alarm_duration_min + 'min'
          : Math.round(d.alarm_duration_min/60) + 'h'}`
      : '';
    footerHtml = `
      <div class="ov-alarm-active">
        <span class="ov-alarm-icon">${icon}</span>
        <span class="ov-alarm-text">${first.description} ${dur}</span>
      </div>
      <span class="${isAlarm ? 'ov-alarm-badge-count' : 'ov-alarm-badge-warn'}">${d.alarm_count}</span>
      ${fixTimeHtml(d.avg_fix_min)}`;
  }

  return `
    <div class="${cardClass}" data-id="${d.id}" data-model-id="${d.model_id || 0}">
      <div class="ov-card-header">
        <div class="ov-status-dot ov-status-dot--${d.online ? 'online' : 'offline'}"></div>
        <span class="ov-card-name">${d.name}${sourceBadge}</span>
        <span class="ov-card-addr">@${d.address}</span>
        ${modelBadge}
      </div>
      <div class="ov-card-body">
        ${sensorsHtml}
        ${outputsHtml}
      </div>
      <div class="ov-card-footer">${footerHtml}</div>
      <div class="ov-card-detail-btn">Ver detalhes →</div>
    </div>`;
}

function ovSensor(label, value, unit, colorClass) {
  const val = value != null ? value.toFixed(1) : '—';
  return `<div class="ov-sensor">
    <div class="ov-sensor-label">${label}</div>
    <div class="ov-sensor-value ov-sensor-value--${colorClass}">${val}</div>
    <div class="ov-sensor-unit">${unit}</div>
  </div>`;
}

function fixTimeHtml(avgMin) {
  if (!avgMin) return '';
  const label = avgMin < 60
    ? `${avgMin} min`
    : `${Math.round(avgMin / 60)}h ${avgMin % 60}min`;
  return `<div class="ov-fix-time">
    <span>Tempo médio correção</span>
    <span class="ov-fix-time-val">⏱ ${label}</span>
  </div>`;
}

function tempColor(val, coldLimit, warnLimit) {
  if (val == null) return '';
  if (val < coldLimit) return 'cold';
  if (val > warnLimit) return 'warn';
  return 'ok';
}

function shColor(sh) {
  if (sh == null) return '';
  if (sh > 12) return 'warn';
  if (sh < 3)  return 'warn';
  return 'ok';
}

function processBadgeClass(text) {
  const map = { 'Refrigeração': 'refr', 'Degelo': 'defrost',
                'Economia': 'eco', 'Standby': 'neutral', 'Ventilador': 'eco' };
  return map[text] || 'neutral';
}

// Abre detalhe de um instrumento a partir do card do overview
function openDetail(id, modelId) {
  $('overview-screen').classList.add('hidden');
  $('empty-state').classList.add('hidden');
  selectInstrument(id, modelId);

  // Marca na sidebar
  document.querySelectorAll('.instrument-item').forEach(li => {
    li.classList.toggle('instrument-item--active', Number(li.dataset.id) === id);
  });
}

// ── Lista de instrumentos (sidebar) ───────────────────────────
async function loadInstruments() {
  let instruments;
  try {
    instruments = await API.instruments();
    $('collector-dot').className    = 'dot dot--online';
    $('collector-label').textContent = 'Conectado';
  } catch {
    $('collector-dot').className    = 'dot dot--offline';
    $('collector-label').textContent = 'Sem conexão';
    return;
  }

  const list = $('instrument-list');
  list.innerHTML = '';

  if (!instruments.length) {
    list.innerHTML = '<li class="instrument-item instrument-item--loading">Nenhum instrumento</li>';
    return;
  }

  for (const instr of instruments) {
    const li       = document.createElement('li');
    const lastSeen = instr.last_seen ? new Date(instr.last_seen) : null;
    const ageS     = lastSeen ? (Date.now() - lastSeen.getTime()) / 1000 : 9999;
    const online   = ageS < 90;
    const isEmu    = instr.source === 'emulator';

    li.className = 'instrument-item' + (instr.id === selectedInstrumentId ? ' instrument-item--active' : '');
    li.dataset.id = instr.id;
    li.innerHTML = `
      <span class="instr-dot ${online ? 'instr-dot--online' : 'instr-dot--offline'}"></span>
      <div style="flex:1;min-width:0">
        <div class="instr-name" title="${instr.name}">${instr.name}</div>
        ${instr.model_name ? `<div class="instr-model">${instr.model_name}${isEmu ? ' 🔵' : ''}</div>` : ''}
      </div>
      <span class="instr-addr">@${instr.address}</span>
    `;
    li.addEventListener('click', () => openDetail(instr.id, instr.model_id));
    list.appendChild(li);
  }
}

// ── Seleciona instrumento ──────────────────────────────────────
async function selectInstrument(id, modelId) {
  selectedInstrumentId = id;
  currentModelId       = modelId;

  // Limpa diagnóstico de IA anterior ao trocar de instrumento
  _inlineCaseId = null;
  const aiBox = $('inline-ai-box');
  aiBox.classList.add('hidden');
  $('inline-ai-loading').classList.add('hidden');
  $('inline-ai-content').classList.add('hidden');
  $('inline-ai-confirm').classList.add('hidden');

  document.querySelectorAll('.instrument-item').forEach(li => {
    li.classList.toggle('instrument-item--active', Number(li.dataset.id) === id);
  });

  $('empty-state').classList.add('hidden');
  $('instrument-panel').classList.remove('hidden');

  // Seleciona layout correto
  const isPCT = PCT122E_MODEL_IDS.has(modelId);
  $('layout-tc900e').classList.toggle('hidden', isPCT);
  $('layout-pct122e').classList.toggle('hidden', !isPCT);

  // Reinicia gráfico com séries do modelo
  initChart(isPCT);

  try {
    const history = await API.history(id);
    loadChartHistory(history, isPCT);
  } catch (e) {
    console.warn('Histórico indisponível:', e);
  }

  await refreshState();
}

// ── Polling ────────────────────────────────────────────────────
function startPoll() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (selectedInstrumentId) await refreshState();
  }, POLL_INTERVAL_MS);
}

async function refreshState() {
  if (!selectedInstrumentId) return;
  try {
    const data = await API.state(selectedInstrumentId);
    renderState(data);
    $('last-update').textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR');
  } catch (e) {
    console.warn('Erro ao buscar estado:', e);
    $('badge-online').className   = 'badge badge--offline';
    $('badge-online').textContent = 'Offline';
  }
}

// ── Renderiza estado (dispatcher por modelo) ───────────────────
function renderState(data) {
  const { instrument } = data;

  // Cabeçalho
  $('panel-title').textContent = instrument.name;
  $('panel-meta').textContent  =
    `Endereço RS-485: ${instrument.address}  |  Fonte: ${instrument.source === 'emulator' ? 'Emulador' : 'Sitrad PRO'}  |  ${instrument.status}`;

  // Badge modelo
  if (instrument.model_name) {
    $('badge-model').textContent = instrument.model_name;
    $('badge-model').classList.remove('hidden');
  }

  // Badge status processo
  setProcessBadge(data.control.process_text, data.control.process_status);

  // Badge online
  $('badge-online').className   = `badge ${instrument.online ? 'badge--online' : 'badge--offline'}`;
  $('badge-online').textContent = instrument.online ? 'Online' : 'Offline';

  const isPCT = PCT122E_MODEL_IDS.has(instrument.model_id);
  if (isPCT) {
    renderPCT122E(data);
  } else {
    renderTC900E(data);
  }

  // Alarmes (compartilhado)
  renderAlarms(data.alarms);

  // Gráfico
  pushChartPoint(data, isPCT);
}

// ── Render TC-900E ─────────────────────────────────────────────
function renderTC900E(data) {
  const { sensors, control, outputs, modes, sensor_errors } = data;

  setSensorCard('val-t1', 'card-t1', 'err-s1', sensors.t1, sensor_errors?.s1);
  setSensorCard('val-t2', 'card-t2', 'err-s2', sensors.t2, sensor_errors?.s2);
  setSensorCard('val-t3', 'card-t3', 'err-s3', sensors.t3, sensor_errors?.s3);

  $('val-setpoint').textContent = control.setpoint != null ? control.setpoint.toFixed(1) : '—';
  $('val-diff').textContent = control.differential != null
    ? `Dif: ${control.differential.toFixed(1)} °C` : 'Dif: —';

  setLed('led-refr',       outputs.refrigeration, 'green');
  setLed('led-fan',        outputs.fan,            'green');
  setLed('led-defrost',    outputs.defrost,        'yellow');
  setLed('led-buzzer',     outputs.buzzer,         'red');
  setLed('led-fastfreeze', modes?.fast_freezing,   'blue');
  setLed('led-eco',        modes?.economic_mode,   'blue');
}

// ── Render PCT-122E Plus ───────────────────────────────────────
function renderPCT122E(data) {
  const { sensors, refrigeration, outputs } = data;
  const r = refrigeration || {};

  // Pressões
  setVal('pct-val-p1',    r.p1,      1, 'PSIG');
  setVal('pct-val-p2',    r.p2,      1, 'PSIG');
  setVal('pct-val-tsat1', r.t_sat_p1, 1, '°C');
  setVal('pct-val-tsat2', r.t_sat_p2, 1, '°C');

  // Superaquecimento
  const sh = r.superheat;
  $('pct-val-sh').textContent = sh != null ? sh.toFixed(1) : '—';
  // Bar: 0-20K range
  $('pct-sh-fill').style.width = sh != null ? Math.min(100, (sh / 20) * 100) + '%' : '0%';

  // Subresfriamento
  const sc = r.subcooling;
  $('pct-val-sc').textContent = sc != null ? sc.toFixed(1) : '—';
  $('pct-sc-fill').style.width = sc != null ? Math.min(100, (sc / 15) * 100) + '%' : '0%';

  // Temperaturas
  setVal('pct-val-t1', sensors.t1, 1, '°C');
  setVal('pct-val-t2', sensors.t2, 1, '°C');
  setVal('pct-val-t3', sensors.t3, 1, '°C');
  setVal('pct-val-t4', sensors.t4, 1, '°C');

  // Saídas analógicas
  setAnalog('pct-an1-fill', 'pct-an1-val', r.an1_pct);
  setAnalog('pct-an2-fill', 'pct-an2-val', r.an2_pct);

  // Saídas digitais
  setLed('pct-led-out1', outputs.refrigeration, 'green');
  setLed('pct-led-out2', outputs.fan,            'green');
  setLed('pct-led-out3', outputs.defrost,        'yellow');
}

// ── Helpers ────────────────────────────────────────────────────
function setVal(elId, value, decimals = 1) {
  $(elId).textContent = value != null ? value.toFixed(decimals) : '—';
}

function setSensorCard(valId, cardId, errId, value, hasError) {
  $(valId).textContent = value != null ? value.toFixed(1) : '—';
  const errEl = $(errId);
  if (errEl) {
    if (hasError) {
      errEl.classList.remove('hidden');
      $(cardId).classList.add('card--alarm');
    } else {
      errEl.classList.add('hidden');
      $(cardId).classList.remove('card--alarm');
    }
  }
}

function setLed(ledId, active, color) {
  const el = $(ledId);
  if (!el) return;
  el.className = 'output-led' + (active ? ` output-led--on-${color}` : '');
}

function setAnalog(fillId, valId, pct) {
  $(fillId).style.width   = pct != null ? Math.min(100, Math.max(0, pct)) + '%' : '0%';
  $(valId).textContent    = pct != null ? pct.toFixed(1) + '%' : '—';
}

function setProcessBadge(text, status) {
  const badge = $('badge-status');
  const map = {
    'Refrigeração': 'badge--refr',
    'Degelo':       'badge--defrost',
    'Economia':     'badge--eco',
    'Alarme':       'badge--warn',
    'Standby':      'badge--neutral',
    'Ventilador':   'badge--eco',
  };
  const cls = (text && map[text]) ? map[text] : 'badge--neutral';
  badge.className   = `badge ${cls}`;
  badge.textContent = text || (status != null ? `Status ${status}` : '—');
}

// Causas prováveis pré-fixadas por código de alarme
const ALARM_CAUSES = {
  // Superaquecimento
  ASHL: [
    'Válvula de expansão com defeito ou obstruída',
    'Carga de refrigerante insuficiente (falta de gás)',
    'Filtro secador saturado ou entupido',
    'Sensor de temperatura T1 fora de posição',
  ],
  ASLL: [
    'Válvula de expansão aberta demais (flooding)',
    'Excesso de refrigerante no sistema',
    'Sonda T1 com mau contato ou defeito',
  ],
  // Pressão
  AHP2: [
    'Condensador sujo ou com bloqueio de ar',
    'Ventilador do condensador parado ou com falha',
    'Temperatura ambiente elevada',
    'Válvula de serviço parcialmente fechada',
  ],
  ALP1: [
    'Perda de carga de refrigerante (vazamento)',
    'Evaporador com excesso de gelo (degelo incompleto)',
    'Válvula de expansão fechada ou com defeito',
    'Compressor sem capacidade adequada',
  ],
  AHP1: [
    'Sobrecarga de calor na câmara',
    'Defeito na válvula de expansão (abertura excessiva)',
  ],
  ALP2: [
    'Baixa carga de refrigerante',
    'Compressor com baixa eficiência',
  ],
  // Temperatura
  AHt1: [
    'Gás de sucção superaquecido — verificar expansão',
    'Evaporador com circulação de ar insuficiente',
  ],
  ALt1: [
    'Retorno de líquido ao compressor',
    'Sensor T1 com defeito',
  ],
  AHt2: [
    'Alta temperatura de descarga — verificar condensação',
    'Razão de compressão elevada',
    'Óleo de compressor contaminado',
  ],
  // Temperatura câmara PCT-122E (T3)
  AHt3: [
    'Porta da câmara aberta ou com vedação defeituosa',
    'Compressor ou ventilador do evaporador parado',
    'Degelo não concluído — evaporador com excesso de gelo',
    'Carga de produto acima da capacidade da câmara',
    'Falha no ciclo de refrigeração (verificar P1/P2)',
  ],
  ALt3: [
    'Setpoint muito baixo — verificar parametrização do controlador',
    'Sensor T3 com defeito ou fora de posição',
    'Supercongelamento acidental — verificar válvula de expansão',
  ],
  // Temperatura câmara (TC-900E)
  ALH_T1: [
    'Porta da câmara aberta ou com vedação defeituosa',
    'Compressor ou ventilador parado',
    'Carga de produto acima da capacidade',
  ],
  ALL_T1: [
    'Setpoint muito baixo — verificar parametrização',
    'Sensor com defeito',
  ],
  ALH_PRESS: [
    'Alta pressão no sistema — verificar condensador',
    'Bloqueio no circuito de descarga',
  ],
  ALL_PRESS: [
    'Baixa pressão — verificar carga de refrigerante',
    'Vazamento no circuito',
  ],
};

function renderAlarms(alarms) {
  const list  = $('alarm-list');
  const badge = $('alarm-count');

  if (!alarms || !alarms.length) {
    list.innerHTML = '<div class="alarm-empty">Nenhum alarme ativo ✓</div>';
    badge.classList.add('hidden');
    return;
  }

  badge.classList.remove('hidden');
  badge.textContent = alarms.length;

  list.innerHTML = alarms.map(a => {

    const icon     = a.severity === 'alarm' ? '🔴' : a.severity === 'warning' ? '🟡' : 'ℹ️';
    const cls      = a.severity === 'alarm' ? 'alarm-item--alarm' : a.severity === 'warning' ? 'alarm-item--warning' : 'alarm-item--info';
    const since    = new Date(a.started_at).toLocaleString('pt-BR');
    const causes   = ALARM_CAUSES[a.code] || [];
    const causesHtml = `<div class="alarm-causes">
        ${causes.length ? `
          <div class="alarm-causes-title">Possíveis causas:</div>
          <ul class="alarm-causes-list">
            ${causes.map(c => `<li>${c}</li>`).join('')}
          </ul>` : ''}
        <button class="btn-alarm-ai" onclick="triggerAIFromAlarm()">
          🤖 Analisar com IA
        </button>
      </div>`;

    // Botão / badge de atendimento
    const assumeHtml = a.assumed_by
      ? `<div class="alarm-assumed">
           <span class="alarm-assumed-icon">👷</span>
           <span>Em atendimento por <strong>${a.assumed_by}</strong> desde ${fmtLogTime(a.assumed_at)}</span>
         </div>`
      : `<div class="alarm-assume-row">
           <button class="btn-assume" data-alarm-id="${a.id}">🔔 Assumir atendimento</button>
           <span class="alarm-assume-hint">Registre que você está tratando este alarme</span>
         </div>`;

    return `
      <div class="alarm-item ${cls}" data-alarm-id="${a.id}">
        <span class="alarm-icon">${icon}</span>
        <div class="alarm-body">
          <div class="alarm-desc">${a.description}</div>
          <div class="alarm-meta">
            <span class="alarm-code">${a.code}</span>
            <span class="alarm-time">desde ${since}</span>
          </div>
          ${assumeHtml}
          ${causesHtml}
        </div>
      </div>`;
  }).join('');

  // Wiring dos botões "Assumir atendimento"
  list.querySelectorAll('.btn-assume').forEach(btn => {
    btn.addEventListener('click', () => openAssumeModal(Number(btn.dataset.alarmId)));
  });
}

// ── Modal de aceite de atendimento ────────────────────────────
function openAssumeModal(alarmId) {
  const name = prompt('👷 Seu nome para registrar o atendimento:');
  if (!name || !name.trim()) return;
  assumeAlarm(alarmId, name.trim());
}

async function assumeAlarm(alarmId, technician) {
  try {
    await fetch(`/api/v1/alarms/${alarmId}/assume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ technician }),
    });
    // Atualiza o painel imediatamente
    await refreshState();
    // Toast de notificação simulada
    showNotifToast(`Notificação enviada para a equipe — ${technician} assumiu o atendimento`);
  } catch (e) {
    alert('Erro ao registrar atendimento: ' + e.message);
  }
}

let _toastTimer = null;
function showNotifToast(msg) {
  const toast = $('notif-toast');
  $('notif-toast-text').textContent = msg;
  toast.classList.remove('hidden', 'notif-toast--hide');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.classList.add('notif-toast--hide');
    setTimeout(() => toast.classList.add('hidden'), 500);
  }, 4000);
}

async function triggerAIFromAlarm() {
  if (!selectedInstrumentId) return;

  const box     = $('inline-ai-box');
  const loading = $('inline-ai-loading');
  const content = $('inline-ai-content');

  // Mostra a caixa com loading
  box.classList.remove('hidden');
  loading.classList.remove('hidden');
  content.classList.add('hidden');

  // Scroll suave até a caixa
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const analysis = await DemoAPI.analyze(selectedInstrumentId);
    renderInlineAIResult(analysis);
  } catch (e) {
    loading.classList.add('hidden');
    content.classList.remove('hidden');
    $('inline-ai-resumo').textContent = '⚠ Erro ao conectar com a IA: ' + e.message;
  }
}

function renderInlineAIResult(a) {
  const loading = $('inline-ai-loading');
  const content = $('inline-ai-content');

  // Badge de status
  const badge = $('inline-ai-badge');
  badge.textContent = a.status_geral || '—';
  badge.className   = `inline-ai-badge inline-ai-status--${(a.status_geral || '').toLowerCase()}`;

  $('inline-ai-urgency').textContent = a.urgencia ? '⏱ ' + a.urgencia : '';

  // Conteúdo
  const resumoLimpo = (a.resumo || '').replace(/\s*\[MODO SIMULAÇÃO[^\]]*\]/g, '').trim();
  $('inline-ai-resumo').textContent      = resumoLimpo;
  $('inline-ai-diagnostico').textContent = a.diagnostico   || '—';
  $('inline-ai-causa').textContent       = a.causa_provavel || '—';

  const ul = $('inline-ai-acoes');
  ul.innerHTML = (a.acoes_recomendadas || []).map(ac => `<li>${ac}</li>`).join('');

  const risco = $('inline-ai-risco');
  risco.textContent = 'Risco ao produto: ' + (a.risco_produto || '—');
  risco.className   = `inline-ai-risco inline-ai-risk--${(a.risco_produto || '').toLowerCase()}`;

  $('inline-ai-confianca').textContent = a.confianca
    ? 'Confiança: ' + Math.round(a.confianca * 100) + '%' : '';
  $('inline-ai-source').textContent = a.source === 'claude-api' ? '🤖 Claude API' : '⚙ Análise local';

  loading.classList.add('hidden');
  content.classList.remove('hidden');

  // Reseta e exibe seção de confirmação
  $('inline-correction-form').classList.add('hidden');
  $('inline-confirm-success').classList.add('hidden');
  $('inline-ai-confirm-btns').classList.remove('hidden');
  $('inline-ai-confirm').classList.remove('hidden');
  ['inline-btn-correct','inline-btn-wrong','inline-btn-submit']
    .forEach(id => { if ($(id)) $(id).disabled = false; });
  ['inline-field-cause','inline-field-resolution','inline-field-outcome','inline-field-technician']
    .forEach(id => { if ($(id)) $(id).value = ''; });
}

// ── Confirmação inline ─────────────────────────────────────────
let _inlineCaseId = null;

function initInlineConfirmButtons() {
  $('inline-btn-correct').addEventListener('click', async () => {
    await submitInlineConfirmation({ ai_was_correct: true });
  });

  $('inline-btn-wrong').addEventListener('click', () => {
    $('inline-correction-form').classList.toggle('hidden');
  });

  $('inline-btn-submit').addEventListener('click', async () => {
    const cause = $('inline-field-cause').value.trim();
    if (!cause) {
      $('inline-field-cause').style.borderColor = 'var(--red)';
      $('inline-field-cause').focus();
      return;
    }
    $('inline-field-cause').style.borderColor = '';
    await submitInlineConfirmation({
      ai_was_correct:  false,
      confirmed_cause: cause,
      resolution:      $('inline-field-resolution').value.trim() || undefined,
      outcome:         $('inline-field-outcome').value.trim()     || undefined,
      confirmed_by:    $('inline-field-technician').value.trim()  || 'Técnico',
    });
  });
}

async function submitInlineConfirmation(payload) {
  if (!_inlineCaseId) return;
  ['inline-btn-correct','inline-btn-wrong','inline-btn-submit']
    .forEach(id => { if ($(id)) $(id).disabled = true; });
  try {
    await fetch(`/api/v1/demo/cases/${_inlineCaseId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    $('inline-correction-form').classList.add('hidden');
    $('inline-ai-confirm-btns').classList.add('hidden');
    $('inline-confirm-success').classList.remove('hidden');
    setTimeout(() => $('inline-ai-box').classList.add('hidden'), 1500);
  } catch (e) {
    alert('Erro ao salvar confirmação: ' + e.message);
    ['inline-btn-correct','inline-btn-wrong']
      .forEach(id => { if ($(id)) $(id).disabled = false; });
  }
}

// ── Gráfico Chart.js ───────────────────────────────────────────
function initChart(isPCT = false) {
  if (mainChart) { mainChart.destroy(); mainChart = null; }

  const ctx       = $('chart-main').getContext('2d');
  const gridColor = 'rgba(48,54,61,.5)';
  const tickColor = '#8b949e';

  let datasets, yAxes;

  if (isPCT) {
    $('chart-section-title').textContent = 'HISTÓRICO — PRESSÃO & TEMPERATURA';
    datasets = [
      makeDS('P1 Sucção (PSIG)',   '#388bfd', false, 'yPressure'),
      makeDS('P2 Descarga (PSIG)', '#8957e5', false, 'yPressure'),
      makeDS('T1 Sucção (°C)',     '#3fb950', false, 'yTemp'),
      makeDS('T3 Câmara (°C)',     '#39c5cf', true,  'yTemp'),
    ];
    yAxes = {
      yPressure: {
        type: 'linear', position: 'left',
        ticks: { color: '#388bfd', font: { size: 10 } },
        grid:  { color: gridColor },
        title: { display: true, text: 'PSIG', color: '#388bfd', font: { size: 10 } },
      },
      yTemp: {
        type: 'linear', position: 'right',
        ticks: { color: '#3fb950', font: { size: 10 } },
        grid:  { drawOnChartArea: false },
        title: { display: true, text: '°C', color: '#3fb950', font: { size: 10 } },
      },
    };
  } else {
    $('chart-section-title').textContent = 'HISTÓRICO DE TEMPERATURA';
    datasets = [
      makeDS('T1 Sonda 1 (°C)', '#388bfd'),
      makeDS('T2 Sonda 2 (°C)', '#3fb950'),
      makeDS('T3 Sonda 3 (°C)', '#8957e5'),
      makeDS('Setpoint (°C)',   '#d29922', true),
    ];
    yAxes = {
      y: {
        ticks: { color: tickColor, font: { size: 10 } },
        grid:  { color: gridColor },
        title: { display: true, text: '°C', color: tickColor, font: { size: 10 } },
      },
    };
  }

  mainChart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 200 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: tickColor, font: { size: 11 }, boxWidth: 12 } },
        tooltip: { backgroundColor: '#1e2430', borderColor: '#30363d', borderWidth: 1 },
      },
      scales: {
        x: {
          ticks: { color: tickColor, font: { size: 10 }, maxTicksLimit: 8 },
          grid:  { color: gridColor },
        },
        ...yAxes,
      },
      elements: { point: { radius: 0 }, line: { tension: 0.3, borderWidth: 2 } },
    },
  });
}

function makeDS(label, color, dashed = false, yAxisID = 'y') {
  return {
    label,
    data: [],
    borderColor: color,
    backgroundColor: color + '18',
    borderDash: dashed ? [6, 3] : [],
    fill: false,
    yAxisID,
  };
}

// ── Carrega histórico no gráfico ───────────────────────────────
function loadChartHistory(readings, isPCT = false) {
  if (!mainChart) return;
  mainChart.data.labels = [];
  mainChart.data.datasets.forEach(ds => ds.data = []);

  readings.forEach(r => {
    const ts = fmtTime(r.timestamp);
    mainChart.data.labels.push(ts);
    if (isPCT) {
      mainChart.data.datasets[0].data.push(r.p1  ?? null);
      mainChart.data.datasets[1].data.push(r.p2  ?? null);
      mainChart.data.datasets[2].data.push(r.t1  ?? null);
      mainChart.data.datasets[3].data.push(r.t3  ?? null);
    } else {
      mainChart.data.datasets[0].data.push(r.t1  ?? null);
      mainChart.data.datasets[1].data.push(r.t2  ?? null);
      mainChart.data.datasets[2].data.push(r.t3  ?? null);
      mainChart.data.datasets[3].data.push(r.setpoint ?? null);
    }
  });

  mainChart.update('none');
}

// ── Empurra ponto em tempo real ────────────────────────────────
function pushChartPoint(data, isPCT = false) {
  if (!mainChart) return;
  const MAX = HISTORY_LIMIT;
  const ts  = fmtTime(data.timestamp);
  const r   = data.refrigeration || {};
  const s   = data.sensors;
  const c   = data.control;

  const push = (arr, val) => {
    arr.push(val ?? null);
    if (arr.length > MAX) arr.shift();
  };

  push(mainChart.data.labels, ts);
  if (isPCT) {
    push(mainChart.data.datasets[0].data, r.p1);
    push(mainChart.data.datasets[1].data, r.p2);
    push(mainChart.data.datasets[2].data, s.t1);
    push(mainChart.data.datasets[3].data, s.t3);
  } else {
    push(mainChart.data.datasets[0].data, s.t1);
    push(mainChart.data.datasets[1].data, s.t2);
    push(mainChart.data.datasets[2].data, s.t3);
    push(mainChart.data.datasets[3].data, c.setpoint);
  }

  mainChart.update('none');
}

function fmtTime(isoStr) {
  return new Date(isoStr).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// ══════════════════════════════════════════════════════════════
// RELATÓRIO PDF
// ══════════════════════════════════════════════════════════════

function initReportButton() {
  const toggle = $('btn-report-toggle');
  const menu   = $('report-menu');

  // Abre/fecha menu
  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('hidden');
  });

  // Fecha ao clicar fora
  document.addEventListener('click', () => menu.classList.add('hidden'));

  // Cada opção de período
  menu.querySelectorAll('.report-menu-item').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!selectedInstrumentId) return;
      const hours = btn.dataset.hours;
      menu.classList.add('hidden');

      // Feedback visual
      const orig = toggle.textContent;
      toggle.textContent = '⟳ Gerando...';
      toggle.disabled = true;

      try {
        // Download direto via link
        const url = `/api/v1/instruments/${selectedInstrumentId}/report?hours=${hours}`;
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (e) {
        alert('Erro ao gerar relatório: ' + e.message);
      } finally {
        setTimeout(() => {
          toggle.textContent = orig;
          toggle.disabled = false;
        }, 2000);
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initReportButton();
});

// ══════════════════════════════════════════════════════════════
// PAINEL DE DEMO — INJEÇÃO DE FALHAS + IA
// ══════════════════════════════════════════════════════════════

const DemoAPI = {
  async faults()         { return _get('/api/v1/demo/faults'); },
  async inject(id)       { return _post(`/api/v1/demo/fault/${id}`); },
  async reset()          { return _post('/api/v1/demo/reset'); },
  async analyze(instrId) { return _post(`/api/v1/demo/analyze/${instrId}`); },
};

async function _post(path) {
  const r = await fetch(path, { method: 'POST' });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${path}`);
  return r.json();
}

let activeFaultId = null;

// ── Inicializa painel de demo ──────────────────────────────────
async function initDemoPanel() {
  // FAB abre o painel
  $('demo-fab').addEventListener('click', openDemoPanel);
  $('demo-close').addEventListener('click', closeDemoPanel);
  $('demo-overlay').addEventListener('click', closeDemoPanel);

  // Carrega lista de falhas
  try {
    const faults = await DemoAPI.faults();
    renderFaultButtons(faults);
  } catch (e) {
    console.warn('Demo panel: não foi possível carregar falhas', e);
  }

  // Botão reset
  $('btn-reset').addEventListener('click', async () => {
    $('btn-reset').textContent = '⟳ Normalizando...';
    $('btn-reset').disabled = true;
    try {
      await DemoAPI.reset();
      activeFaultId = null;
      document.querySelectorAll('.fault-btn').forEach(b => {
        b.classList.remove('fault-btn--active', 'fault-btn--active-warn');
      });
      showDemoResult('⚪', 'Sistema Normalizado',
        'Parâmetros restaurados para operação normal.',
        'Aguarde ~30s para ver os valores retornarem ao normal no dashboard.');
      $('btn-analyze').disabled = true;
      $('ai-result').classList.add('hidden');
    } catch (e) {
      alert('Erro ao normalizar: ' + e.message);
    } finally {
      $('btn-reset').textContent = '⚪ Normalizar Sistema';
      $('btn-reset').disabled = false;
    }
  });

  // Botão analisar
  $('btn-analyze').addEventListener('click', async () => {
    if (!selectedInstrumentId) return;
    $('ai-result').classList.add('hidden');
    $('ai-loading').classList.remove('hidden');
    $('btn-analyze').disabled = true;
    try {
      const analysis = await DemoAPI.analyze(selectedInstrumentId);
      renderAIResult(analysis);
    } catch (e) {
      alert('Erro na análise: ' + e.message);
    } finally {
      $('ai-loading').classList.add('hidden');
      $('btn-analyze').disabled = false;
    }
  });
}

function openDemoPanel() {
  $('demo-overlay').classList.remove('hidden');
  $('demo-panel').classList.remove('hidden');
}

function closeDemoPanel() {
  $('demo-overlay').classList.add('hidden');
  $('demo-panel').classList.add('hidden');
}

function renderFaultButtons(faults) {
  const grid = $('demo-faults-grid');
  grid.innerHTML = '';

  faults.forEach(fault => {
    const btn = document.createElement('button');
    btn.className = 'fault-btn';
    btn.dataset.faultId = fault.id;
    const sevClass = fault.severity === 'critical' ? 'fault-btn-sev-critical' : 'fault-btn-sev-warning';

    btn.innerHTML = `
      <span class="fault-btn-icon">${fault.icon}</span>
      <div class="fault-btn-body">
        <div class="fault-btn-label ${sevClass}">${fault.label}</div>
        <div class="fault-btn-desc">${fault.description}</div>
      </div>
    `;

    btn.addEventListener('click', () => injectFault(fault, btn));
    grid.appendChild(btn);
  });
}

let countdownTimer = null;

async function injectFault(fault, btnEl) {
  document.querySelectorAll('.fault-btn').forEach(b => {
    b.classList.remove('fault-btn--active', 'fault-btn--active-warn');
  });
  const activeClass = fault.severity === 'critical' ? 'fault-btn--active' : 'fault-btn--active-warn';
  btnEl.classList.add(activeClass);
  btnEl.style.opacity = '0.6';

  try {
    const result = await DemoAPI.inject(fault.id);
    activeFaultId = fault.id;

    showDemoResult(
      fault.icon,
      result.label,
      result.description + '\n' + result.hint,
      result.message
    );

    // Oculta resultado anterior e reseta confirmação
    $('ai-result').classList.add('hidden');
    $('ai-confirm-section').classList.add('hidden');

    // Countdown 10s — emulador responde imediatamente ao vivo
    // (sem precisar esperar o coletor de 30s, pois analyze lê ao vivo)
    startAnalyzeCountdown(10);

  } catch (e) {
    alert('Erro ao injetar falha: ' + e.message);
    btnEl.classList.remove(activeClass);
  } finally {
    btnEl.style.opacity = '1';
  }
}

function startAnalyzeCountdown(seconds) {
  const btn = $('btn-analyze');
  btn.disabled = true;
  clearInterval(countdownTimer);

  let remaining = seconds;
  btn.textContent = `🤖 Analisar com IA (${remaining}s)`;

  countdownTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      clearInterval(countdownTimer);
      btn.disabled = false;
      btn.textContent = '🤖 Analisar com IA';
    } else {
      btn.textContent = `🤖 Analisar com IA (${remaining}s)`;
    }
  }, 1000);
}

function showDemoResult(icon, label, desc, msg) {
  $('demo-result-icon').textContent  = icon;
  $('demo-result-label').textContent = label;
  $('demo-result-desc').textContent  = desc;
  $('demo-result-msg').textContent   = msg;
  $('demo-result').classList.remove('hidden');
}

let currentCaseId = null;

function renderAIResult(a) {
  // Badge de status
  const badge = $('ai-status-badge');
  badge.textContent  = a.status_geral;
  badge.className    = `ai-status-badge ai-status--${a.status_geral}`;

  $('ai-urgency').textContent     = '⏱ ' + a.urgencia;

  // Banner e badge de simulação
  const isSimMode = a.resumo && a.resumo.includes('[MODO SIMULAÇÃO');
  $('ai-sim-banner').classList.toggle('hidden', !isSimMode);
  $('ai-source').textContent = a.source === 'claude-api'
    ? (isSimMode ? '🔵 Claude API — Modo Simulação' : '🤖 Claude API')
    : '⚙ Análise local';
  $('ai-source').style.color = isSimMode ? 'var(--cyan)' : '';

  // Remove nota de simulação do resumo antes de exibir (fica no badge)
  const resumoLimpo = (a.resumo || '').replace(/\s*\[MODO SIMULAÇÃO[^\]]*\]/g, '').trim();
  $('ai-resumo').textContent = resumoLimpo;
  $('ai-diagnostico').textContent = a.diagnostico;
  $('ai-causa').textContent       = a.causa_provavel;

  const ul = $('ai-acoes-list');
  ul.innerHTML = (a.acoes_recomendadas || [])
    .map(acao => `<li>${acao}</li>`).join('');

  const riskBadge = $('ai-risk-badge');
  riskBadge.textContent = a.risco_produto;
  riskBadge.className   = `ai-risk-badge ai-risk--${a.risco_produto}`;

  $('ai-confianca').textContent = a.confianca
    ? Math.round(a.confianca * 100) + '%' : '—';

  // Guarda case_id para confirmação (demo panel e inline)
  currentCaseId  = a.case_id || null;
  _inlineCaseId  = a.case_id || null;

  // Reseta formulário de confirmação
  $('ai-correction-form').classList.add('hidden');
  $('ai-confirm-success').classList.add('hidden');
  $('ai-confirm-section').classList.remove('hidden');
  ['btn-ai-correct','btn-ai-wrong'].forEach(id => { $(id).disabled = false; });
  ['field-confirmed-cause','field-resolution','field-outcome','field-technician']
    .forEach(id => { $(id).value = ''; });

  $('ai-result').classList.remove('hidden');
}

// ── Confirmação de diagnóstico ─────────────────────────────────
function initConfirmButtons() {
  // Botão "IA acertou"
  $('btn-ai-correct').addEventListener('click', async () => {
    if (!currentCaseId) return;
    await submitConfirmation({ ai_was_correct: true });
  });

  // Botão "Corrigir"
  $('btn-ai-wrong').addEventListener('click', () => {
    $('ai-correction-form').classList.toggle('hidden');
  });

  // Salvar correção
  $('btn-confirm-submit').addEventListener('click', async () => {
    const cause = $('field-confirmed-cause').value.trim();
    if (!cause) {
      $('field-confirmed-cause').focus();
      $('field-confirmed-cause').style.borderColor = 'var(--red)';
      return;
    }
    $('field-confirmed-cause').style.borderColor = '';
    await submitConfirmation({
      ai_was_correct:  false,
      confirmed_cause: cause,
      resolution:      $('field-resolution').value.trim() || undefined,
      outcome:         $('field-outcome').value.trim() || undefined,
      confirmed_by:    $('field-technician').value.trim() || 'Técnico',
    });
  });
}

async function submitConfirmation(payload) {
  if (!currentCaseId) return;
  ['btn-ai-correct','btn-ai-wrong','btn-confirm-submit'].forEach(id => {
    if ($(id)) $(id).disabled = true;
  });
  try {
    await _post(`/api/v1/demo/cases/${currentCaseId}/confirm`);
    // Chama endpoint com payload
    await fetch(`/api/v1/demo/cases/${currentCaseId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    $('ai-correction-form').classList.add('hidden');
    $('ai-confirm-success').classList.remove('hidden');
    $('ai-confirm-section').querySelector('.ai-confirm-btns').classList.add('hidden');
    setTimeout(() => closeDemoPanel(), 1500);
  } catch (e) {
    alert('Erro ao salvar confirmação: ' + e.message);
    ['btn-ai-correct','btn-ai-wrong'].forEach(id => { if ($(id)) $(id).disabled = false; });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initConfirmButtons();
  initInlineConfirmButtons();
});

// Inicializa demo ao carregar
document.addEventListener('DOMContentLoaded', () => {
  initDemoPanel();
  initNormalizeButton();
});

// ── Botão Normalizar fixo na sidebar ──────────────────────────
function initNormalizeButton() {
  const btn = $('btn-normalize-sidebar');
  const msg = $('normalize-msg');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '⟳ Normalizando...';
    msg.classList.add('hidden');
    try {
      await _post('/api/v1/demo/reset');
      // Limpa estado ativo no painel de demo também
      activeFaultId = null;
      document.querySelectorAll('.fault-btn').forEach(b =>
        b.classList.remove('fault-btn--active', 'fault-btn--active-warn'));
      $('ai-result').classList.add('hidden');
      $('demo-result').classList.add('hidden');
      $('btn-analyze').disabled = true;

      msg.classList.remove('hidden');
      setTimeout(() => msg.classList.add('hidden'), 4000);
    } catch (e) {
      alert('Erro ao normalizar: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '🔄 Normalizar Emulador';
    }
  });
}
