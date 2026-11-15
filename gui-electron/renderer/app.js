/**
 * System Optimization Toolkit - Electron Renderer Process
 * 
 * Gerencia UI, tabs, comunicação com backend via IPC
 */

// Estado da aplicação
const state = {
  activeTab: 0,
  tabs: ['audit', 'tune', 'bench', 'memory', 'logs'],
  running: false,
  progress: null,
  logs: [],
  logFilters: {
    levels: { info: true, warn: true, error: true, debug: true, success: true, progress: true },
    sources: { gui: true, 'backend-stdout': true, 'backend-stderr': true }
  },
  autoScrollLogs: true,
  coreStatus: { exists: false },
  systemInfo: { cpu: 0, ram: { used: 0, total: 0 } },
  auditData: { packages: null, boot: null, hardware: null, overclock: null, actionPlan: null },
  benchResults: null
};

// Elementos DOM
const elements = {};

// Inicialização
document.addEventListener('DOMContentLoaded', async () => {
  cacheElements();
  setupEventListeners();
  setupIPCListeners();
  await loadConfig();
  startSystemMonitor();
});

// Cache de elementos DOM
function cacheElements() {
  // Tab bar
  elements.tabButtons = document.querySelectorAll('.tab-btn');
  elements.tabPanels = document.querySelectorAll('.tab-panel');
  
  // Header
  elements.coreStatus = document.getElementById('core-status');
  elements.statusIndicator = document.getElementById('status-indicator');
  elements.statusText = document.getElementById('status-text');
  elements.systemMonitor = document.getElementById('system-monitor');
  
  // Progress
  elements.progressContainer = document.getElementById('progress-container');
  elements.progressFill = document.getElementById('progress-fill');
  elements.progressInfo = document.getElementById('progress-info');
  
  // Status bar
  elements.statusLeft = document.getElementById('status-left');
  elements.footerCpu = document.getElementById('footer-cpu');
  elements.footerRam = document.getElementById('footer-ram');
  
  // Audit
  elements.btnAuditRun = document.getElementById('btn-audit-run');
  elements.auditShowJson = document.getElementById('audit-show-json');
  elements.auditContent = document.getElementById('audit-content');
  
  // Tune
  elements.btnTuneRun = document.getElementById('btn-tune-run');
  elements.tuneDryRun = document.getElementById('tune-dry-run');
  elements.tuneApply = document.getElementById('tune-apply');
  elements.tuneRestore = document.getElementById('tune-restore');
  elements.tuneGovernor = document.getElementById('tune-governor');
  elements.tuneCStates = document.getElementById('tune-cstates');
  elements.tuneThp = document.getElementById('tune-thp');
  elements.tuneSchedLatency = document.getElementById('tune-sched-latency');
  elements.tuneSchedMigCost = document.getElementById('tune-sched-mig-cost');
  elements.tuneIrqbalance = document.getElementById('tune-irqbalance');
  elements.tuneMaskThermald = document.getElementById('tune-mask-thermald');
  elements.tuneMaskTuned = document.getElementById('tune-mask-tuned');
  elements.tuneMaskPpd = document.getElementById('tune-mask-ppd');
  elements.tuneContent = document.getElementById('tune-content');
  
  // Bench
  elements.btnBenchRun = document.getElementById('btn-bench-run');
  elements.btnBenchSuite = document.getElementById('btn-bench-suite');
  elements.btnBenchReport = document.getElementById('btn-bench-report');
  elements.benchQuick = document.getElementById('bench-quick');
  elements.benchOutput = document.getElementById('bench-output');
  elements.benchContent = document.getElementById('bench-content');
  elements.benchResults = document.getElementById('bench-results');
  
  // Memory
  elements.btnMemRun = document.getElementById('btn-mem-run');
  elements.memDryRun = document.getElementById('mem-dry-run');
  elements.memCron = document.getElementById('mem-cron');
  elements.memDropCaches = document.getElementById('mem-drop-caches');
  elements.memCompaction = document.getElementById('mem-compaction');
  elements.memSwap = document.getElementById('mem-swap');
  elements.memCheckCompaction = document.getElementById('mem-check-compaction');
  elements.memCheckHugepages = document.getElementById('mem-check-hugepages');
  elements.memContent = document.getElementById('mem-content');
  
  // Logs
  elements.logBody = document.getElementById('log-body');
  elements.logAutoScroll = document.getElementById('log-auto-scroll');
  elements.btnLogsClear = document.getElementById('btn-logs-clear');
  elements.btnLogsExport = document.getElementById('btn-logs-export');
  elements.logFilters = document.querySelectorAll('.log-filter');
}

// Event Listeners UI
function setupEventListeners() {
  // Tab switching
  elements.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => switchTab(parseInt(btn.dataset.tab)));
  });
  
  // Audit
  elements.btnAuditRun.addEventListener('click', () => runAudit());
  elements.auditShowJson.addEventListener('change', () => renderAuditContent());
  
  // Tune
  elements.btnTuneRun.addEventListener('click', () => runTune());
  [elements.tuneDryRun, elements.tuneApply, elements.tuneRestore].forEach(el => {
    el.addEventListener('change', updateTuneButtons);
  });
  
  // Bench
  elements.btnBenchRun.addEventListener('click', () => runBenchmark());
  elements.btnBenchSuite.addEventListener('click', () => runBenchmarkSuite());
  elements.btnBenchReport.addEventListener('click', () => generateReport());
  
  // Memory
  elements.btnMemRun.addEventListener('click', () => runMemory());
  
  // Logs
  elements.btnLogsClear.addEventListener('click', () => clearLogs());
  elements.btnLogsExport.addEventListener('click', () => exportLogs());
  elements.logAutoScroll.addEventListener('change', (e) => {
    state.autoScrollLogs = e.target.checked;
    window.sysopt.setConfig({ autoScrollLogs: state.autoScrollLogs });
  });
  elements.logFilters.forEach(filter => {
    filter.addEventListener('change', updateLogFilters);
  });
}

// IPC Listeners
function setupIPCListeners() {
  const { sysopt } = window;
  
  // Backend events
  sysopt.onBackendStarted(({ command }) => {
    state.running = true;
    updateRunningState();
    setStatus(`Executando: ${command.join(' ')}`);
    showProgress(`Iniciando ${command[0]}...`, 0);
  });
  
  sysopt.onBackendProgress(({ stage, current, total, percent, message }) => {
    state.progress = { stage, current, total, percent, message };
    updateProgress();
  });
  
  sysopt.onBackendResult(({ section, data }) => {
    handleBackendResult(section, data);
  });
  
  sysopt.onBackendComplete(({ exitCode, durationMs, message }) => {
    state.running = false;
    state.progress = null;
    updateRunningState();
    hideProgress();
    setStatus(`Concluído (código ${exitCode}) em ${durationMs}ms: ${message}`);
    addLog(exitCode === 0 ? 'success' : 'error', `Backend: ${message}`, 'backend-stdout');
  });
  
  sysopt.onBackendLog(({ level, message }) => {
    addLog(level, message, 'backend-stderr');
  });
  
  sysopt.onBackendError(({ message }) => {
    state.running = false;
    state.progress = null;
    updateRunningState();
    hideProgress();
    setStatus(`Erro: ${message}`);
    addLog('error', message, 'backend-stderr');
  });
  
  sysopt.onCoreStatus(({ path, exists }) => {
    state.coreStatus = { path, exists };
    updateCoreStatus();
    updateRunningState();
  });
  
  sysopt.onConfigChanged(({ autoScrollLogs }) => {
    state.autoScrollLogs = autoScrollLogs;
    elements.logAutoScroll.checked = autoScrollLogs;
  });
  
  sysopt.onLogsCleared(() => {
    state.logs = [];
    renderLogs();
  });
  
  // Initial config
  sysopt.getConfig().then(config => {
    state.activeTab = config.activeTab || 0;
    state.autoScrollLogs = config.autoScrollLogs !== false;
    elements.logAutoScroll.checked = state.autoScrollLogs;
    switchTab(state.activeTab);
  });
}

// Carrega configuração inicial
async function loadConfig() {
  const config = await window.sysopt.getConfig();
  state.activeTab = config.activeTab || 0;
  state.autoScrollLogs = config.autoScrollLogs !== false;
  elements.logAutoScroll.checked = state.autoScrollLogs;
  switchTab(state.activeTab);
}

// Sistema de monitoramento (CPU/RAM)
function startSystemMonitor() {
  updateSystemInfo();
  setInterval(updateSystemInfo, 5000);
}

async function updateSystemInfo() {
  try {
    const info = await window.sysopt.getSystemInfo();
    state.systemInfo = info;
    renderSystemMonitor();
  } catch (e) {
    console.error('Erro ao obter info do sistema:', e);
  }
}

function renderSystemMonitor() {
  const { cpus, totalMemory, freeMemory } = state.systemInfo;
  const usedMemory = totalMemory - freeMemory;
  const usedMB = Math.round(usedMemory / 1024 / 1024);
  const totalMB = Math.round(totalMemory / 1024 / 1024);
  
  // Header
  elements.systemMonitor.textContent = `CPU: ${state.systemInfo.cpu || '--'}% | RAM: ${usedMB}/${totalMB} MB`;
  
  // Footer
  elements.footerCpu.textContent = `CPU: ${state.systemInfo.cpu || '--'}%`;
  elements.footerRam.textContent = `RAM: ${usedMB}/${totalMB} MB`;
}

// Tab Management
function switchTab(index) {
  if (index < 0 || index >= state.tabs.length) return;
  
  state.activeTab = index;
  state.tabs.forEach((_, i) => {
    elements.tabButtons[i].classList.toggle('active', i === index);
    elements.tabPanels[i].style.display = i === index ? 'flex' : 'none';
  });
  
  window.sysopt.saveActiveTab(index);
  
  // Refresh content on tab switch
  if (index === 4) renderLogs(); // Logs tab
}

// Core Status
function updateCoreStatus() {
  const { exists, path } = state.coreStatus;
  elements.statusIndicator.className = 'status-indicator ' + (exists ? 'ok' : 'error');
  elements.statusText.textContent = exists ? `core.sh: ✓ Encontrado` : `core.sh: ✗ Não encontrado (${path})`;
  elements.coreStatus.title = path;
}

function updateRunningState() {
  const running = state.running || !state.coreStatus.exists;
  const buttons = [
    elements.btnAuditRun, elements.btnTuneRun, elements.btnBenchRun,
    elements.btnBenchSuite, elements.btnBenchReport, elements.btnMemRun
  ];
  buttons.forEach(btn => {
    if (btn) btn.disabled = running;
  });
}

// Progress Bar
function showProgress(stage, percent) {
  elements.progressContainer.style.display = 'block';
  elements.progressFill.style.width = `${percent}%`;
  elements.progressInfo.textContent = `${stage}: ${percent}%`;
}

function updateProgress() {
  if (!state.progress) return;
  const { stage, current, total, percent, message } = state.progress;
  elements.progressFill.style.width = `${percent}%`;
  elements.progressInfo.textContent = `${stage}: ${percent}% (${current}/${total}) ${message}`;
}

function hideProgress() {
  elements.progressContainer.style.display = 'none';
  elements.progressFill.style.width = '0%';
  elements.progressInfo.textContent = '';
}

// Status Bar
function setStatus(message) {
  elements.statusLeft.textContent = message;
}

// ===== AUDIT =====
function runAudit() {
  window.sysopt.executeCommand(['audit', '--json']);
}

function handleBackendResult(section, data) {
  if (section.startsWith('audit_')) {
    const key = section.replace('audit_', '');
    state.auditData[key] = data;
    renderAuditContent();
  } else if (section.startsWith('tune_')) {
    addLog('info', `Tuning: ${section}`, 'backend-stdout');
  } else if (section.startsWith('bench_')) {
    state.benchResults = data;
    renderBenchResults(data);
  } else if (section.startsWith('memory_')) {
    addLog('info', `Memory: ${section}`, 'backend-stdout');
  }
}

function renderAuditContent() {
  const showJson = elements.auditShowJson.checked;
  const data = state.auditData;
  
  if (!data.packages && !data.boot && !data.hardware && !data.overclock && !data.actionPlan) {
    elements.auditContent.innerHTML = '<div class="empty-state">Nenhum dado — execute a auditoria</div>';
    return;
  }
  
  let html = '';
  
  // Packages
  html += renderAuditSection('📦 Pacotes', data.packages, showJson, renderPackages);
  
  // Boot
  html += renderAuditSection('🚀 Inicialização (Boot)', data.boot, showJson, renderBoot);
  
  // Hardware
  html += renderAuditSection('🖥️ Hardware', data.hardware, showJson, renderHardware);
  
  // Overclock
  html += renderAuditSection('⚡ Overclock', data.overclock, showJson, renderOverclock);
  
  // Action Plan
  html += renderAuditSection('📋 Plano de Ação', data.actionPlan, showJson, renderActionPlan);
  
  elements.auditContent.innerHTML = html;
  
  // Add event listeners to details/summary
  elements.auditContent.querySelectorAll('details summary').forEach(summary => {
    summary.addEventListener('click', (e) => {
      // Allow default behavior
    });
  });
}

function renderAuditSection(title, data, showJson, renderer) {
  if (!data) {
    return `<details class="audit-section"><summary>${title}</summary><div class="audit-section-content"><div class="empty-state">Nenhum dado</div></div></details>`;
  }
  
  if (showJson) {
    return `<details class="audit-section"><summary>${title}</summary><div class="audit-section-content"><pre class="audit-json">${escapeHtml(JSON.stringify(data, null, 2))}</pre></div></details>`;
  }
  
  return `<details class="audit-section" open><summary>${title}</summary><div class="audit-section-content">${renderer(data)}</div></details>`;
}

function renderPackages(data) {
  let html = '';
  if (data.orphans?.length) {
    html += `<div class="audit-item"><strong>Pacotes órfãos (${data.orphans.length}):</strong></div>`;
    data.orphans.forEach(pkg => html += `<div class="audit-item">  • ${escapeHtml(pkg)}</div>`);
  }
  if (data.single_use?.length) {
    html += `<div class="audit-item"><strong>Uso único/sem binários (${data.single_use.length}):</strong></div>`;
    data.single_use.forEach(pkg => html += `<div class="audit-item">  • ${escapeHtml(pkg)}</div>`);
  }
  return html || '<div class="empty-state">Nenhum pacote problemático detectado</div>';
}

function renderBoot(data) {
  let html = '';
  if (data.total_time) html += `<div class="audit-item"><strong>Tempo total:</strong> ${escapeHtml(data.total_time)}</div>`;
  if (data.bottlenecks?.length) {
    html += `<div class="audit-item"><strong>Serviços mais lentos:</strong></div>`;
    data.bottlenecks.forEach((svc, i) => html += `<div class="audit-item">  ${i + 1}. ${escapeHtml(svc)}</div>`);
  }
  if (data.critical_chain) {
    html += `<div class="audit-item"><strong>Cadeia crítica:</strong></div><pre class="audit-json">${escapeHtml(data.critical_chain)}</pre>`;
  }
  return html || '<div class="empty-state">Nenhum dado de boot</div>';
}

function renderHardware(data) {
  let html = '';
  if (data.cpu) {
    html += `<div class="audit-item"><strong>CPU:</strong></div>`;
    Object.entries(data.cpu).forEach(([k, v]) => html += `<div class="audit-item">  ${k}: ${escapeHtml(String(v))}</div>`);
  }
  if (data.gpu?.length) {
    html += `<div class="audit-item"><strong>GPU:</strong></div>`;
    data.gpu.forEach(g => html += `<div class="audit-item">  • ${escapeHtml(g)}</div>`);
  }
  if (data.ram) {
    html += `<div class="audit-item"><strong>Memória:</strong></div>`;
    Object.entries(data.ram).forEach(([k, v]) => html += `<div class="audit-item">  ${k}: ${escapeHtml(String(v))}</div>`);
  }
  if (data.thermal) {
    html += `<div class="audit-item"><strong>Térmica:</strong></div>`;
    Object.entries(data.thermal).forEach(([k, v]) => html += `<div class="audit-item">  ${k}: ${escapeHtml(String(v))}</div>`);
  }
  return html || '<div class="empty-state">Nenhum dado de hardware</div>';
}

function renderOverclock(data) {
  let html = '';
  if (data.viability) {
    const color = data.viability.includes('Viável') ? 'var(--accent-green)' : 
                  data.viability.includes('Requer') ? 'var(--accent-yellow)' : 'var(--accent-red)';
    html += `<div class="audit-item" style="color: ${color}"><strong>Viabilidade:</strong> ${escapeHtml(data.viability)}</div>`;
  }
  if (data.details?.length) {
    data.details.forEach(d => html += `<div class="audit-item">  • ${escapeHtml(d)}</div>`);
  }
  return html || '<div class="empty-state">Nenhum dado de overclock</div>';
}

function renderActionPlan(data) {
  if (Array.isArray(data)) {
    let html = '';
    data.forEach((action, i) => html += `<div class="audit-item">${i + 1}. ${escapeHtml(action)}</div>`);
    return html;
  }
  return '<div class="empty-state">Nenhum plano de ação</div>';
}

// ===== TUNE =====
function updateTuneButtons() {
  const hasAction = elements.tuneDryRun.checked || elements.tuneApply.checked || elements.tuneRestore.checked;
  elements.btnTuneRun.disabled = state.running || !state.coreStatus.exists || !hasAction;
}

function runTune() {
  const args = ['tune'];
  if (elements.tuneDryRun.checked) args.push('--dry-run');
  if (elements.tuneApply.checked) args.push('--apply');
  if (elements.tuneRestore.checked) args.push('--restore');
  
  // Governor
  args.push('--governor', elements.tuneGovernor.value);
  
  // C-States
  args.push('--cstates', elements.tuneCStates.value);
  
  // THP
  args.push('--thp', elements.tuneThp.value);
  
  // Scheduler
  if (elements.tuneSchedLatency.checked) args.push('--sched-latency');
  if (elements.tuneSchedMigCost.checked) args.push('--sched-mig-cost');
  
  // IRQ Balance
  if (elements.tuneIrqbalance.checked) args.push('--irqbalance');
  
  // Power services
  if (elements.tuneMaskThermald.checked) args.push('--mask-thermald');
  if (elements.tuneMaskTuned.checked) args.push('--mask-tuned');
  if (elements.tuneMaskPpd.checked) args.push('--mask-ppd');
  
  window.sysopt.executeCommand(args);
}

// ===== BENCHMARK =====
function runBenchmark() {
  const args = ['bench'];
  if (elements.benchQuick.checked) args.push('--quick');
  const output = elements.benchOutput.value.trim();
  if (output) args.push('--output', output);
  window.sysopt.executeCommand(args);
}

function runBenchmarkSuite() {
  window.sysopt.executeCommand(['test-suite']);
}

function generateReport() {
  window.sysopt.executeCommand(['report']);
}

function renderBenchResults(data) {
  elements.benchResults.style.display = 'block';
  
  let html = '<h3>📊 Resultados do Benchmark</h3>';
  
  if (data.stress_ng) {
    html += renderBenchSection('stress-ng', data.stress_ng);
  }
  if (data.sysbench_cpu) {
    html += renderBenchSection('sysbench CPU', data.sysbench_cpu);
  }
  if (data.sysbench_memory) {
    html += renderBenchSection('sysbench Memory', data.sysbench_memory);
  }
  if (data.context_switch) {
    html += renderBenchSection('Context Switch', data.context_switch);
  }
  if (data.frequency) {
    html += renderBenchSection('Frequência', data.frequency);
  }
  
  elements.benchResults.innerHTML = html;
}

function renderBenchSection(title, data) {
  let html = `<div class="bench-result-item"><h4>${title}</h4>`;
  Object.entries(data).forEach(([key, value]) => {
    let cls = '';
    if (typeof value === 'string' && value.includes('%')) {
      const num = parseFloat(value);
      cls = num > 0 ? 'positive' : num < 0 ? 'negative' : '';
    }
    html += `<div class="bench-metric"><span class="label">${key}:</span><span class="value ${cls}">${value}</span></div>`;
  });
  html += '</div>';
  return html;
}

// ===== MEMORY =====
function runMemory() {
  const args = ['memory'];
  if (elements.memDryRun.checked) args.push('--dry-run');
  if (elements.memCron.value !== 'none') {
    args.push('--cron', elements.memCron.value);
  } else if (elements.memCron.value === 'remove') {
    args.push('--remove-cron');
  }
  if (elements.memDropCaches.checked) args.push('--drop-caches');
  if (elements.memCompaction.checked) args.push('--compaction');
  if (elements.memSwap.checked) args.push('--swap');
  if (elements.memCheckCompaction.checked) args.push('--check-compaction');
  if (elements.memCheckHugepages.checked) args.push('--check-hugepages');
  
  window.sysopt.executeCommand(args);
}

// ===== LOGS =====
function addLog(level, message, source) {
  const entry = {
    timestamp: new Date(),
    level,
    message,
    source
  };
  
  state.logs.push(entry);
  if (state.logs.length > 5000) state.logs.shift();
  
  renderLogs();
}

function updateLogFilters() {
  elements.logFilters.forEach(filter => {
    const type = filter.dataset.level ? 'levels' : 'sources';
    const key = filter.dataset.level || filter.dataset.source;
    state.logFilters[type][key] = filter.checked;
  });
  renderLogs();
}

function renderLogs() {
  const { levels, sources } = state.logFilters;
  
  const filtered = state.logs.filter(log => 
    levels[log.level] && sources[log.source]
  );
  
  elements.logBody.innerHTML = filtered.map(log => `
    <tr>
      <td class="log-time">${log.timestamp.toLocaleTimeString()}</td>
      <td class="log-level ${log.level}">${log.level.toUpperCase()}</td>
      <td class="log-source">${log.source}</td>
      <td class="log-message">${escapeHtml(log.message)}</td>
    </tr>
  `).join('');
  
  if (state.autoScrollLogs) {
    elements.logBody.scrollTop = elements.logBody.scrollHeight;
  }
}

function clearLogs() {
  state.logs = [];
  renderLogs();
  window.sysopt.setConfig({}); // Trigger logs-cleared event
}

function exportLogs() {
  const { levels, sources } = state.logFilters;
  const filtered = state.logs.filter(log => levels[log.level] && sources[log.source]);
  
  const csv = ['timestamp,level,source,message', 
    ...filtered.map(log => `"${log.timestamp.toISOString()}","${log.level}","${log.source}","${log.message.replace(/"/g, '""')}"`)
  ].join('\n');
  
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sysopt-logs-${new Date().toISOString().slice(0,19).replace(/:/g, '-')}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// Utilitários
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}