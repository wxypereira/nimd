//! Tab: Performance Tuning

use eframe::egui::{self, Ui, RichText, Color32, Button};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;
use crate::app::GuiEvent;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

pub struct TuneTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<GuiEvent>,
    dry_run: bool,
    show_advanced: bool,
    governor_options: Vec<String>,
    selected_governor: usize,
}

impl TuneTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            dry_run: true,
            show_advanced: false,
            governor_options: vec![
                "performance".to_string(),
                "powersave".to_string(),
                "schedutil".to_string(),
                "ondemand".to_string(),
                "conservative".to_string(),
            ],
            selected_governor: 0,
        }
    }
}

impl Tab for TuneTab {
    fn name(&self) -> &str { "Tuning" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("⚡ Performance Tuning");
        ui.label("⚠️ Requer root. Desabilita C-states, ativa turbo, fixa governor=performance.");
        ui.separator();
        
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.dry_run, "🔍 Dry-run (simular apenas)");
            ui.checkbox(&mut self.show_advanced, "⚙️ Opções avançadas");
        });
        
        if self.show_advanced {
            ui.horizontal(|ui| {
                ui.label("Governor:");
                egui::ComboBox::from_id_salt("governor")
                    .selected_text(&self.governor_options[self.selected_governor])
                    .show_ui(ui, |ui| {
                        for (i, gov) in self.governor_options.iter().enumerate() {
                            ui.selectable_value(&mut self.selected_governor, i, gov);
                        }
                    });
            });
        }
        
        ui.separator();
        
        ui.horizontal(|ui| {
            let apply_btn = ui.add_enabled(
                !*running,
                Button::new(if self.dry_run { "▶ Simular Tuning" } else { "⚡ Aplicar Tuning" })
                    .fill(if self.dry_run { Color32::from_rgb(70, 130, 180) } else { Color32::from_rgb(180, 70, 70) })
            );
            if apply_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::Tune {
                    apply: !self.dry_run,
                    restore: false,
                    dry_run: self.dry_run,
                });
            }
            
            let restore_btn = ui.add_enabled(
                !*running,
                Button::new("🔄 Restaurar Padrão").fill(Color32::from_rgb(100, 100, 180))
            );
            if restore_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::Tune {
                    apply: false,
                    restore: true,
                    dry_run: false,
                });
            }
        });
        
        ui.separator();
        
        egui::CollapsingHeader::new("📋 O que o tuning faz")
            .default_open(true)
            .show(ui, |ui| {
                ui.label("1. CPU Governor → performance (frequência fixa no máximo)");
                ui.label("2. Intel PState → no_hwp + turbo ativado");
                ui.label("3. C-States → desabilitados (latência zero, consumo alto)");
                ui.label("4. Scheduler → latency_ns=1ms, migration_cost_ns=5ms");
                ui.label("5. THP → always (Transparent Huge Pages)");
                ui.label("6. Serviços → thermald, tuned, power-profiles-daemon mascarados");
                ui.label("7. IRQBalance → desabilitado");
            });
        
        ui.separator();
        ui.colored_label(Color32::YELLOW, "⚠️ MONITORE TEMPERATURAS: watch -n1 sensors");
        ui.colored_label(Color32::RED, "❌ NÃO USE EM LAPTOPS SEM REFRIGERAÇÃO ADEQUADA");
    }
}