//! Tab: Benchmarks

use eframe::egui::{self, Ui, RichText, Color32, Button};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;
use crate::app::GuiEvent;
use serde_json::Value;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

pub struct BenchTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<GuiEvent>,
    quick: bool,
    output_path: String,
    last_result: Option<Value>,
}

impl BenchTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            quick: false,
            output_path: "".to_string(),
            last_result: None,
        }
    }
}

impl Tab for BenchTab {
    fn name(&self) -> &str { "Benchmark" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("📊 Benchmark Suite");
        ui.separator();
        
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.quick, "⚡ Quick mode (30s por teste, sem memory/ctx)");
            if self.output_path.is_empty() {
                ui.label("Output: auto (data/benchmarks/benchmark_<timestamp>_<governor>.log)");
            } else {
                ui.label(format!("Output: {}", self.output_path));
            }
        });
        
        ui.separator();
        
        ui.horizontal(|ui| {
            let bench_btn = ui.add_enabled(
                !*running,
                Button::new("▶ Executar Benchmark").fill(Color32::from_rgb(70, 130, 180))
            );
            if bench_btn.clicked() {
                *running = true;
                let output = if self.output_path.is_empty() { None } else { Some(self.output_path.clone()) };
                let _ = backend.execute(BackendCommand::Bench { quick: self.quick, output });
            }
            
            let suite_btn = ui.add_enabled(
                !*running,
                Button::new("🧪 Suite Comparativa Completa").fill(Color32::from_rgb(100, 150, 100))
            );
            if suite_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::TestSuite {
                    baseline_only: false,
                    performance_only: false,
                    memory_only: false,
                    combined_only: false,
                    quick: self.quick,
                    no_restore: false,
                });
            }
        });
        
        ui.separator();
        
        if let Some(result) = &self.last_result {
            egui::CollapsingHeader::new("📈 Último Resultado")
                .default_open(true)
                .show(ui, |ui| {
                    if let Some(file) = result.get("benchmark_log").and_then(|v| v.get("file")).and_then(|v| v.as_str()) {
                        ui.label(format!("Log: {}", file));
                    }
                    ui.label("Use 'Gerar Relatório' para análise completa");
                });
        }
        
        ui.separator();
        
        if ui.button("📄 Gerar Relatório Comparativo").clicked() {
            let _ = backend.execute(BackendCommand::Report);
        }
    }
    
    fn on_backend_result(&mut self, section: &str, data: &Value) {
        if section == "benchmark_log" {
            self.last_result = Some(data.clone());
        }
    }
}