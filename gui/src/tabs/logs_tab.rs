//! Tab: Logs em Tempo Real

use eframe::egui::{self, Ui, RichText, Color32};
use crate::widgets::LogView;
use crate::app::LogLevel;
use crate::tabs::Tab;
use crate::backend::Backend;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

pub struct LogsTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    log_view: LogView,
}

impl LogsTab {
    pub fn new(logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>) -> Self {
        Self {
            logs,
            log_view: LogView::new(),
        }
    }
}

impl Tab for LogsTab {
    fn name(&self) -> &str { "Logs" }
    
    fn draw(&mut self, ui: &mut Ui, _backend: &mut Backend, _running: &mut bool) {
        ui.heading("📋 Logs em Tempo Real");
        ui.separator();
        
        ui.horizontal(|ui| {
            self.log_view.draw_filters(ui);
            ui.separator();
            if ui.button("🗑️ Limpar").clicked() {
                self.logs.lock().unwrap().clear();
            }
        });
        
        ui.separator();
        
        let logs = self.logs.lock().unwrap();
        self.log_view.draw(ui, &logs);
    }
}