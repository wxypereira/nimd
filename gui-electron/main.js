/**
 * System Optimization Toolkit - Electron Main Process
 * 
 * Comunicação com core.sh via JSON Lines protocol
 * Gerencia janela, menu, persistência e processos backend
 */

const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const Store = require('electron-store');

// Configuração de persistência
const store = new Store({
  name: 'sysopt-gui',
  defaults: {
    windowBounds: { width: 1200, height: 800 },
    activeTab: 0,
    corePath: '../scripts/core.sh',
    autoScrollLogs: true,
    lastBenchmarkOutput: ''
  }
});

let mainWindow = null;
let backendProcess = null;
let backendBuffer = '';

// Logs globais (em memória, max 5000)
const globalLogs = [];
const MAX_LOGS = 5000;

function createWindow() {
  const bounds = store.get('windowBounds');
  
  mainWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: 900,
    minHeight: 600,
    title: 'System Optimization Toolkit',
    icon: path.join(__dirname, 'assets/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    },
    show: false
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer/index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    // Verifica se core.sh existe
    checkCoreScript();
  });

  mainWindow.on('close', () => {
    // Salva bounds
    store.set('windowBounds', mainWindow.getBounds());
    // Mata processo backend se rodando
    if (backendProcess) {
      backendProcess.kill('SIGTERM');
      setTimeout(() => {
        if (backendProcess && !backendProcess.killed) {
          backendProcess.kill('SIGKILL');
        }
      }, 2000);
    }
  });

  // Menu da aplicação
  createMenu();
}

function createMenu() {
  const template = [
    {
      label: 'Arquivo',
      submenu: [
        {
          label: 'Abrir pasta de dados',
          click: () => shell.openPath(path.join(__dirname, '..', 'data'))
        },
        { type: 'separator' },
        { role: 'quit', label: 'Sair' }
      ]
    },
    {
      label: 'Configurações',
      submenu: [
        {
          label: 'Auto-scroll logs',
          type: 'checkbox',
          checked: store.get('autoScrollLogs'),
          click: (item) => {
            store.set('autoScrollLogs', item.checked);
            sendToRenderer('config-changed', { autoScrollLogs: item.checked });
          }
        },
        {
          label: 'Limpar logs globais',
          click: () => {
            globalLogs.length = 0;
            sendToRenderer('logs-cleared');
          }
        }
      ]
    },
    {
      label: 'Ajuda',
      submenu: [
        {
          label: 'Sobre',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'Sobre System Optimization Toolkit',
              message: 'System Optimization Toolkit v1.0.0',
              detail: 'Diagnóstico passivo, tuning agressivo e benchmark comparativo para Linux (Arch/Manjaro/CachyOS)\n\nArquitetura: Python (Auditor) + Bash (Tuning/Benchmarks) + Electron (GUI)'
            });
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function checkCoreScript() {
  const corePath = store.get('corePath');
  const fullPath = path.resolve(__dirname, corePath);
  const exists = require('fs').existsSync(fullPath);
  
  sendToRenderer('core-status', { path: corePath, exists });
}

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data);
  }
}

// ===== BACKEND PROCESS MANAGEMENT =====

function executeBackendCommand(command) {
  const corePath = store.get('corePath');
  const fullPath = path.resolve(__dirname, corePath);
  
  if (!require('fs').existsSync(fullPath)) {
    sendToRenderer('backend-error', { message: `core.sh não encontrado em: ${fullPath}` });
    return;
  }

  // Kill previous process if running
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill('SIGTERM');
  }

  backendBuffer = '';
  sendToRenderer('backend-started', { command });

  backendProcess = spawn(fullPath, command, {
    cwd: path.dirname(fullPath),
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  backendProcess.stdout.on('data', (data) => {
    backendBuffer += data.toString();
    processBackendOutput();
  });

  backendProcess.stderr.on('data', (data) => {
    const lines = data.toString().split('\n').filter(l => l.trim());
    lines.forEach(line => {
      const parsed = parseLogLine(line);
      sendToRenderer('backend-log', { level: parsed.level, message: parsed.message });
      addGlobalLog(parsed.level, parsed.message, 'backend-stderr');
    });
  });

  backendProcess.on('close', (code) => {
    sendToRenderer('backend-complete', { exitCode: code });
    backendProcess = null;
  });

  backendProcess.on('error', (err) => {
    sendToRenderer('backend-error', { message: `Erro ao executar: ${err.message}` });
    backendProcess = null;
  });
}

function processBackendOutput() {
  const lines = backendBuffer.split('\n');
  // Mantém a última linha incompleta no buffer
  backendBuffer = lines.pop() || '';
  
  lines.forEach(line => {
    line = line.trim();
    if (!line) return;
    
    try {
      const json = JSON.parse(line);
      handleBackendJsonEvent(json);
    } catch (e) {
      // Não é JSON, trata como log
      const parsed = parseLogLine(line);
      sendToRenderer('backend-log', { level: parsed.level, message: parsed.message });
      addGlobalLog(parsed.level, parsed.message, 'backend-stdout');
    }
  });
}

function handleBackendJsonEvent(json) {
  const type = json.type;
  
  switch (type) {
    case 'progress':
      sendToRenderer('backend-progress', {
        stage: json.stage,
        current: json.current,
        total: json.total,
        percent: json.percent,
        message: json.message
      });
      addGlobalLog('progress', `${json.stage}: ${json.percent}% (${json.current}/${json.total})`, 'backend-stdout');
      break;
      
    case 'result':
      sendToRenderer('backend-result', {
        section: json.section,
        data: json.data
      });
      addGlobalLog('success', `Resultado: ${json.section}`, 'backend-stdout');
      break;
      
    case 'complete':
      sendToRenderer('backend-complete', {
        exitCode: json.exit_code,
        durationMs: json.duration_ms,
        message: json.message
      });
      break;
      
    default:
      console.warn('Evento backend desconhecido:', type);
  }
}

function parseLogLine(line) {
  const bracketMatch = line.match(/^\[([A-Z]+)\]\s*(.*)$/);
  if (bracketMatch) {
    return { level: bracketMatch[1].toLowerCase(), message: bracketMatch[2] };
  }
  return { level: 'info', message: line };
}

function addGlobalLog(level, message, source) {
  globalLogs.push({
    timestamp: new Date().toISOString(),
    level,
    message,
    source
  });
  if (globalLogs.length > MAX_LOGS) {
    globalLogs.shift();
  }
}

// ===== IPC HANDLERS =====

ipcMain.handle('get-config', () => ({
  corePath: store.get('corePath'),
  autoScrollLogs: store.get('autoScrollLogs'),
  activeTab: store.get('activeTab'),
  lastBenchmarkOutput: store.get('lastBenchmarkOutput')
}));

ipcMain.handle('set-config', (event, config) => {
  Object.keys(config).forEach(key => {
    if (store.has(key)) store.set(key, config[key]);
  });
  return true;
});

ipcMain.handle('execute-command', (event, command) => {
  executeBackendCommand(command);
  return true;
});

ipcMain.handle('get-logs', () => globalLogs);

ipcMain.handle('get-system-info', async () => {
  // Retorna info básica do sistema
  const os = require('os');
  return {
    platform: os.platform(),
    arch: os.arch(),
    cpus: os.cpus().length,
    totalMemory: os.totalmem(),
    freeMemory: os.freemem(),
    hostname: os.hostname(),
    uptime: os.uptime()
  };
});

ipcMain.on('save-tab', (event, tabIndex) => {
  store.set('activeTab', tabIndex);
});

// App lifecycle
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// Security: Prevent new window creation
app.on('web-contents-created', (event, contents) => {
  contents.on('new-window', (e, url) => {
    e.preventDefault();
    shell.openExternal(url);
  });
});