//! Tab: Auditoria do Sistema

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use eframe::egui::{self, Ui, RichText, Color32};
use serde_json::Value;
use crossbeam_channel::Sender;
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;
use crate::app::GuiEvent;

pub struct AuditTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: Sender<GuiEvent>,
    packages: Option<Value>,
    boot: Option<Value>,
    hardware: Option<Value>,
    overclock: Option<Value>,
    action_plan: Option<Value>,
    show_json: bool,
}

impl AuditTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: Sender<GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            packages: None,
            boot: None,
            hardware: None,
            overclock: None,
            action_plan: None,
            show_json: false,
        }
    }
}

impl Tab for AuditTab {
    fn name(&self) -> &str { "Auditoria" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.horizontal(|ui| {
            ui.heading("🔍 Auditoria do Sistema");
            ui.separator();
            let btn = ui.add_enabled(!*running, egui::Button::new("▶ Executar Auditoria"));
            if btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::Audit { json: true });
            }
            ui.checkbox(&mut self.show_json, "Mostrar JSON bruto");
        });
        
        ui.separator();
        
        egui::ScrollArea::vertical().show(ui, |ui| {
            self.render_section(ui, "📦 Pacotes", &self.packages, |ui, data| {
                self.render_packages(ui, data);
            });
            
            self.render_section(ui, "🚀 Inicialização (Boot)", &self.boot, |ui, data| {
                self.render_boot(ui, data);
            });
            
            self.render_section(ui, "🖥️ Hardware", &self.hardware, |ui, data| {
                self.render_hardware(ui, data);
            });
            
            self.render_section(ui, "⚡ Overclock", &self.overclock, |ui, data| {
                self.render_overclock(ui, data);
            });
            
            self.render_section(ui, "📋 Plano de Ação", &self.action_plan, |ui, data| {
                self.render_action_plan(ui, data);
            });
        });
    }
    
    fn on_backend_result(&mut self, section: &str, data: &Value) {
        match section {
            "packages" => self.packages = Some(data.clone()),
            "boot" => self.boot = Some(data.clone()),
            "hardware" => self.hardware = Some(data.clone()),
            "overclock" => self.overclock = Some(data.clone()),
            "action_plan" => self.action_plan = Some(data.clone()),
            _ => {}
        }
    }
}

impl AuditTab {
    fn render_section<F>(&self, ui: &mut Ui, title: &str, data: &Option<Value>, render: F)
    where F: FnOnce(&mut Ui, &Value) {
        egui::CollapsingHeader::new(title)
            .default_open(true)
            .show(ui, |ui| {
                if let Some(data) = data {
                    if self.show_json {
                        ui.code(format!("{}", serde_json::to_string_pretty(data).unwrap()));
                    } else {
                        render(ui, data);
                    }
                } else {
                    ui.label(RichText::new("Nenhum dado — execute a auditoria").color(Color32::GRAY));
                }
            });
    }
    
    fn render_packages(&self, ui: &mut Ui, data: &Value) {
        if let Some(orphans) = data.get("orphans").and_then(|v| v.as_array()) {
            ui.label(RichText::new(format!("Pacotes órfãos: {}", orphans.len())).strong());
            for pkg in orphans {
                ui.label(format!("  • {}", pkg.as_str().unwrap_or("")));
            }
        }
        if let Some(single) = data.get("single_use").and_then(|v| v.as_array()) {
            ui.label(RichText::new(format!("Uso único/sem binários: {}", single.len())).strong());
            for pkg in single {
                ui.label(format!("  • {}", pkg.as_str().unwrap_or("")));
            }
        }
    }
    
    fn render_boot(&self, ui: &mut Ui, data: &Value) {
        if let Some(time) = data.get("total_time").and_then(|v| v.as_str()) {
            ui.label(format!("Tempo total: {}", time));
        }
        if let Some(bottlenecks) = data.get("bottlenecks").and_then(|v| v.as_array()) {
            ui.label("Serviços mais lentos:");
            for (i, svc) in bottlenecks.iter().enumerate() {
                ui.label(format!("  {}. {}", i + 1, svc.as_str().unwrap_or("")));
            }
        }
        if let Some(chain) = data.get("critical_chain").and_then(|v| v.as_str()) {
            ui.separator();
            ui.label("Cadeia crítica:");
            ui.code(chain);
        }
    }
    
    fn render_hardware(&self, ui: &mut Ui, data: &Value) {
        if let Some(cpu) = data.get("cpu").and_then(|v| v.as_object()) {
            ui.label(RichText::new("CPU").strong());
            for (k, v) in cpu {
                ui.label(format!("  {}: {}", k, v.as_str().unwrap_or("")));
            }
        }
        if let Some(gpu) = data.get("gpu").and_then(|v| v.as_array()) {
            ui.label(RichText::new("GPU").strong());
            for g in gpu { ui.label(format!("  • {}", g.as_str().unwrap_or(""))); }
        }
        if let Some(ram) = data.get("ram").and_then(|v| v.as_object()) {
            ui.label(RichText::new("Memória").strong());
            for (k, v) in ram { ui.label(format!("  {}: {}", k, v.as_str().unwrap_or(""))); }
        }
        if let Some(thermal) = data.get("thermal").and_then(|v| v.as_object()) {
            ui.label(RichText::new("Térmica").strong());
            for (k, v) in thermal { ui.label(format!("  {}: {}", k, v)); }
        }
    }
    
    fn render_overclock(&self, ui: &mut Ui, data: &Value) {
        if let Some(viability) = data.get("viability").and_then(|v| v.as_str()) {
            let color = match viability {
                v if v.contains("Viável") => Color32::GREEN,
                v if v.contains("Requer") => Color32::YELLOW,
                _ => Color32::RED,
            };
            ui.label(RichText::new(format!("Viabilidade: {}", viability)).color(color).strong());
        }
        if let Some(details) = data.get("details").and_then(|v| v.as_array()) {
            for d in details { ui.label(format!("  • {}", d.as_str().unwrap_or(""))); }
        }
    }
    
    fn render_action_plan(&self, ui: &mut Ui, data: &Value) {
        if let Some(plan) = data.as_array() {
            for (i, action) in plan.iter().enumerate() {
                ui.label(format!("{}. {}", i + 1, action.as_str().unwrap_or("")));
            }
        }
    }
}