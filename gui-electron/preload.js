/**
 * Preload Script - Secure Bridge between Main and Renderer
 * 
 * Expõe APIs seguras via contextBridge
 */

const { contextBridge, ipcRenderer } = require('electron');

// API exposta para o renderer
const api = {
  // Configuração
  getConfig: () => ipcRenderer.invoke('get-config'),
  setConfig: (config) => ipcRenderer.invoke('set-config', config),
  
  // Execução de comandos backend
  executeCommand: (command) => ipcRenderer.invoke('execute-command', command),
  
  // Logs
  getLogs: () => ipcRenderer.invoke('get-logs'),
  
  // Info do sistema
  getSystemInfo: () => ipcRenderer.invoke('get-system-info'),
  
  // Eventos do backend (listeners)
  onBackendStarted: (callback) => {
    ipcRenderer.on('backend-started', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-started');
  },
  onBackendProgress: (callback) => {
    ipcRenderer.on('backend-progress', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-progress');
  },
  onBackendResult: (callback) => {
    ipcRenderer.on('backend-result', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-result');
  },
  onBackendComplete: (callback) => {
    ipcRenderer.on('backend-complete', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-complete');
  },
  onBackendLog: (callback) => {
    ipcRenderer.on('backend-log', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-log');
  },
  onBackendError: (callback) => {
    ipcRenderer.on('backend-error', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('backend-error');
  },
  onCoreStatus: (callback) => {
    ipcRenderer.on('core-status', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('core-status');
  },
  onConfigChanged: (callback) => {
    ipcRenderer.on('config-changed', (_, data) => callback(data));
    return () => ipcRenderer.removeAllListeners('config-changed');
  },
  onLogsCleared: (callback) => {
    ipcRenderer.on('logs-cleared', () => callback());
    return () => ipcRenderer.removeAllListeners('logs-cleared');
  },
  
  // Salvar tab ativa
  saveActiveTab: (tabIndex) => ipcRenderer.send('save-tab', tabIndex)
};

// Expor API no contexto isolado
contextBridge.exposeInMainWorld('sysopt', api);