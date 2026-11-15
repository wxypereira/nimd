//! Trait comum para todas as tabs

use crate::backend::Backend;
use crate::widgets::LogView;
use eframe::egui::{self, Ui};

pub trait Tab: Send + Sync {
    fn name(&self) -> &str;
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool);
    fn on_backend_result(&mut self, section: &str, data: &serde_json::Value) {}
}

pub mod audit_tab;
pub mod tune_tab;
pub mod bench_tab;
pub mod memory_tab;
pub mod logs_tab;

pub use audit_tab::AuditTab;
pub use tune_tab::TuneTab;
pub use bench_tab::BenchTab;
pub use memory_tab::MemoryTab;
pub use logs_tab::LogsTab;