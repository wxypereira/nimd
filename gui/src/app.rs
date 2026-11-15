//! Aplicação principal — Estado global, tabs, persistência.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use eframe::egui::{self};
use egui::Context;
use serde::{Deserialize, Serialize};
use tracing::{info};

use crate::backend::{Backend, BackendEvent};
use crate::tabs::{Tab, AuditTab, TuneTab, BenchTab, MemoryTab, LogsTab};

/// Estado persistido entre sessões
#[derive(Debug, Default, Serialize, Deserialize, Clone)]
struct PersistedState {
    window_size: Option<[f32; 2]>,
    active_tab: usize,
    last_core_path: String,
    benchmark_quick: bool,
    auto_scroll_logs: bool,
}

/// Eventos internos da GUI
#[derive(Debug, Clone)]
pub enum GuiEvent {
    BackendEvent(BackendEvent),
    TabChanged(usize),
    RequestShutdown,
}

/// Entry de log
#[derive(Debug, Clone)]
pub struct LogEntry {
    pub timestamp: chrono::DateTime<chrono::Local>,
    pub level: LogLevel,
    pub message: String,
    pub source: LogSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LogLevel {
    Info,
    Warn,
    Error,
    Debug,
    Success,
    Progress,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LogSource {
    Gui,
    BackendStdout,
    BackendStderr,
}

#[derive(Debug, Clone)]
struct ProgressInfo {
    stage: String,
    current: u32,
    total: u32,
    percent: u32,
    message: String,
}

/// Aplicação principal
pub struct SysOptApp {
    persisted: PersistedState,
    backend: Backend,
    tabs: Vec<Box<dyn Tab>>,
    active_tab: usize,
    global_logs: Arc<Mutex<VecDeque<LogEntry>>>,
    auto_scroll: bool,
    operation_running: bool,
    operation_start: Option<Instant>,
    progress: Option<ProgressInfo>,
    gui_event_tx: crossbeam_channel::Sender<GuiEvent>,
    gui_event_rx: crossbeam_channel::Receiver<GuiEvent>,
}

impl SysOptApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        let persisted: PersistedState = cc.storage
            .and_then(|s| eframe::get_value(s, "sysopt_state"))
            .unwrap_or_default();
        
        let (gui_event_tx, gui_event_rx) = crossbeam_channel::unbounded();
        let global_logs = Arc::new(Mutex::new(VecDeque::with_capacity(5000)));
        
        let core_path = persisted.last_core_path.clone();
        let core_path = if core_path.is_empty() { "../scripts/core.sh".to_string() } else { core_path };
        
        // Canal separado para eventos do backend → GUI
        let (backend_event_tx, _backend_event_rx) = crossbeam_channel::unbounded();
        let backend = Backend::new(core_path, backend_event_tx, global_logs.clone());
        
        let tabs: Vec<Box<dyn Tab>> = vec![
            Box::new(AuditTab::new(global_logs.clone(), gui_event_tx.clone())),
            Box::new(TuneTab::new(global_logs.clone(), gui_event_tx.clone())),
            Box::new(BenchTab::new(global_logs.clone(), gui_event_tx.clone())),
            Box::new(MemoryTab::new(global_logs.clone(), gui_event_tx.clone())),
            Box::new(LogsTab::new(global_logs.clone())),
        ];
        
        let auto_scroll = persisted.auto_scroll_logs;
        let active_tab = persisted.active_tab.min(4);
        
        Self {
            persisted,
            backend,
            tabs,
            active_tab,
            global_logs,
            auto_scroll,
            operation_running: false,
            operation_start: None,
            progress: None,
            gui_event_tx,
            gui_event_rx,
        }
    }
    
    pub fn load_persisted_state(&mut self, ctx: &Context) {
        if let Some(size) = self.persisted.window_size {
            ctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(egui::Vec2::new(size[0], size[1])));
        }
    }
    
    fn save_persisted_state(&mut self, ctx: &Context) {
        let outer_rect = ctx.input(|i| i.viewport().outer_rect);
        if let Some(rect) = outer_rect {
            self.persisted.window_size = Some([rect.width(), rect.height()]);
        }
        self.persisted.active_tab = self.active_tab;
        self.persisted.auto_scroll_logs = self.auto_scroll;
        
        ctx.data_mut(|d| {
            d.insert_persisted(egui::Id::new("sysopt_state"), self.persisted.clone());
        });
    }
}

impl eframe::App for SysOptApp {
    fn update(&mut self, ctx: &Context, _frame: &mut eframe::Frame) {
        // Processa eventos do backend
        while let Ok(event) = self.backend.try_recv_event() {
            self.handle_backend_event(event);
        }
        
        // Processa eventos da GUI (tabs)
        while let Ok(event) = self.gui_event_rx.try_recv() {
            match event {
                GuiEvent::TabChanged(idx) => self.active_tab = idx,
                GuiEvent::RequestShutdown => ctx.send_viewport_cmd(egui::ViewportCommand::Close),
                GuiEvent::BackendEvent(_) => {} // Não deveria acontecer neste canal
            }
        }
        
        // Atualiza backend
        self.backend.poll();
        
        // Menu bar
        egui::TopBottomPanel::top("menu_bar").show(ctx, |ui| {
            self.show_menu_bar(ui);
        });
        
        // Status bar
        egui::TopBottomPanel::bottom("status_bar").show(ctx, |ui| {
            self.show_status_bar(ui);
        });
        
        // Tab bar
        egui::TopBottomPanel::top("tab_bar").show(ctx, |ui| {
            self.show_tab_bar(ui);
        });
        
        // Área central
        egui::CentralPanel::default().show(ctx, |ui| {
            if let Some(tab) = self.tabs.get_mut(self.active_tab) {
                tab.draw(ui, &mut self.backend, &mut self.operation_running);
            }
        });
        
        self.save_persisted_state(ctx);
        
        if self.operation_running {
            ctx.request_repaint_after(Duration::from_millis(100));
        }
    }
    
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        self.backend.shutdown();
        info!("Application exiting");
    }
}

impl SysOptApp {
    fn show_menu_bar(&mut self, ui: &mut egui::Ui) {
        egui::menu::bar(ui, |ui| {
            ui.menu_button("Arquivo", |ui| {
                if ui.button("Abrir pasta de dados").clicked() {
                    let _ = opener::open("../data");
                    ui.close_menu();
                }
                ui.separator();
                if ui.button("Sair").clicked() {
                    self.gui_event_tx.send(GuiEvent::RequestShutdown).ok();
                }
            });
            
            ui.menu_button("Configurações", |ui| {
                ui.checkbox(&mut self.auto_scroll, "Auto-scroll logs");
                if ui.button("Limpar logs globais").clicked() {
                    self.global_logs.lock().unwrap().clear();
                }
            });
            
            ui.menu_button("Ajuda", |ui| {
                if ui.button("Sobre").clicked() {
                    // TODO: About dialog
                }
            });
            
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if self.operation_running {
                    ui.spinner();
                    ui.label("Processando...");
                }
            });
        });
    }
    
    fn show_tab_bar(&mut self, ui: &mut egui::Ui) {
        let tab_names = ["🔍 Auditoria", "⚡ Tuning", "📊 Benchmark", "🧠 Memória", "📋 Logs"];
        
        ui.horizontal(|ui| {
            for (idx, name) in tab_names.iter().enumerate() {
                let selected = self.active_tab == idx;
                if ui.selectable_label(selected, *name).clicked() {
                    self.active_tab = idx;
                    self.gui_event_tx.send(GuiEvent::TabChanged(idx)).ok();
                }
            }
            
            ui.separator();
            
            let core_exists = std::path::Path::new(self.backend.core_path()).exists();
            let color = if core_exists { egui::Color32::GREEN } else { egui::Color32::RED };
            ui.colored_label(color, format!("core.sh: {}", 
                if core_exists { "✓ Encontrado" } else { "✗ Não encontrado" }));
        });
    }
    
    fn show_status_bar(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            if let Some(progress) = &self.progress {
                ui.label(&progress.stage);
                ui.add(egui::ProgressBar::new(progress.percent as f32 / 100.0)
                    .show_percentage()
                    .animate(true));
                ui.label(format!("{}/{}", progress.current, progress.total));
            } else if self.operation_running {
                ui.spinner();
                ui.label("Executando...");
                if let Some(start) = self.operation_start {
                    let elapsed = start.elapsed().as_secs();
                    ui.label(format!("{}s", elapsed));
                }
            } else {
                ui.label("Pronto");
            }
            
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let mut sys = sysinfo::System::new_all();
                sys.refresh_all();
                let cpu_usage = sys.global_cpu_info().cpu_usage() as u32;
                let mem_used = sys.used_memory() / 1024 / 1024;
                let mem_total = sys.total_memory() / 1024 / 1024;
                ui.label(format!("CPU: {}% | RAM: {}/{} MB", cpu_usage, mem_used, mem_total));
            });
        });
    }
    
    fn handle_backend_event(&mut self, event: BackendEvent) {
        match event {
            BackendEvent::Progress { stage, current, total, percent, message } => {
                self.progress = Some(ProgressInfo { stage: stage.clone(), current, total, percent, message: message.clone() });
                self.add_log(LogLevel::Progress, &format!("{}: {}% ({}/{})", stage, percent, current, total), LogSource::BackendStdout);
            }
            BackendEvent::Result { section, data } => {
                self.add_log(LogLevel::Success, &format!("Resultado: {} → {}", section, data), LogSource::BackendStdout);
                if let Some(tab) = self.tabs.get_mut(self.active_tab) {
                    tab.on_backend_result(&section, &data);
                }
            }
            BackendEvent::Complete { exit_code, duration_ms, message } => {
                self.operation_running = false;
                self.operation_start = None;
                self.progress = None;
                
                let level = if exit_code == 0 { LogLevel::Success } else { LogLevel::Error };
                self.add_log(level, &format!("Concluído (código {}) em {}ms: {}", exit_code, duration_ms, message), LogSource::BackendStdout);
            }
            BackendEvent::Log { level, message } => {
                let log_level = match level.as_str() {
                    "INFO" => LogLevel::Info,
                    "WARN" => LogLevel::Warn,
                    "ERROR" => LogLevel::Error,
                    "DEBUG" => LogLevel::Debug,
                    "OK" => LogLevel::Success,
                    _ => LogLevel::Info,
                };
                self.add_log(log_level, &message, LogSource::BackendStderr);
            }
            BackendEvent::Error { message } => {
                self.add_log(LogLevel::Error, &message, LogSource::BackendStderr);
            }
        }
    }
    
    fn add_log(&self, level: LogLevel, message: &str, source: LogSource) {
        let mut logs = self.global_logs.lock().unwrap();
        logs.push_back(LogEntry {
            timestamp: chrono::Local::now(),
            level,
            message: message.to_string(),
            source,
        });
        if logs.len() > 5000 {
            logs.pop_front();
        }
    }
}