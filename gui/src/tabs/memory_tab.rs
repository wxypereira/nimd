//! Tab: Memory Optimization

use eframe::egui::{self, Ui, RichText, Color32, Button};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;
use crate::app::GuiEvent;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

pub struct MemoryTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<GuiEvent>,
    cron_mode: String,
    remove_cron: bool,
    dry_run: bool,
}

impl MemoryTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            cron_mode: "daily".to_string(),
            remove_cron: false,
            dry_run: true,
        }
    }
}

impl Tab for MemoryTab {
    fn name(&self) -> &str { "Memória" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("🧠 Memory Optimization");
        ui.label("Executa: sync → drop_caches=3 → verifica CONFIG_COMPACTION → ativa vm.compaction_memory");
        ui.separator();
        
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.dry_run, "🔍 Dry-run");
            ui.checkbox(&mut self.remove_cron, "🗑️ Remover cron jobs existentes");
        });
        
        if !self.remove_cron {
            ui.horizontal(|ui| {
                ui.label("Cron:");
                egui::ComboBox::from_id_salt("memory_cron")
                    .selected_text(&self.cron_mode)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.cron_mode, "none".to_string(), "Nenhum (execução única)");
                        ui.selectable_value(&mut self.cron_mode, "hourly".to_string(), "Horário");
                        ui.selectable_value(&mut self.cron_mode, "daily".to_string(), "Diário (03:00)");
                        ui.selectable_value(&mut self.cron_mode, "weekly".to_string(), "Semanal (Dom 03:00)");
                    });
            });
        }
        
        ui.separator();
        
        let btn_text = if self.remove_cron { "🗑️ Remover Crons" } 
            else if self.dry_run { "▶ Simular" } 
            else { "⚡ Aplicar" };
        let btn_color = if self.remove_cron { Color32::from_rgb(180, 70, 70) }
            else if self.dry_run { Color32::from_rgb(70, 130, 180) }
            else { Color32::from_rgb(100, 150, 100) };
        
        let btn = ui.add_enabled(!*running, Button::new(btn_text).fill(btn_color));
        if btn.clicked() {
            *running = true;
            let cron = if self.cron_mode == "none" { None } else { Some(self.cron_mode.clone()) };
            let _ = backend.execute(BackendCommand::Memory { 
                cron, 
                remove_cron: self.remove_cron, 
                dry_run: self.dry_run 
            });
        }
        
        ui.separator();
        
        egui::CollapsingHeader::new("ℹ️ O que faz")
            .default_open(true)
            .show(ui, |ui| {
                ui.label("1. sync — Garante buffers de disco escritos");
                ui.label("2. echo 3 > /proc/sys/vm/drop_caches — Libera pagecache, dentries, inodes");
                ui.label("3. Verifica CONFIG_COMPACTION=y em múltiplos locais do kernel");
                ui.label("4. Se suportado: echo 1 > /proc/sys/vm/compaction_memory");
                ui.label("5. Opcional: Instala cron job idempotente (remove antes de adicionar)");
            });
        
        ui.separator();
        ui.colored_label(Color32::YELLOW, "⚠️ drop_caches=3 pode causar latência temporária se muita memória suja");
        ui.colored_label(Color32::YELLOW, "⚠️ Bit errors detectados em testes — verifique hardware RAM");
    }
}