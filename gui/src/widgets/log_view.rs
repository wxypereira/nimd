//! Widget: Caixa de logs com cores, filtros, auto-scroll, busca

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use eframe::egui::{self, Ui, RichText, Color32, TextStyle, ScrollArea, TextEdit};
use crate::app::{LogEntry, LogLevel, LogSource};

pub struct LogView {
    filter_level: Option<LogLevel>,
    filter_source: Option<LogSource>,
    search_text: String,
    auto_scroll: bool,
    max_lines: usize,
}

impl LogView {
    pub fn new() -> Self {
        Self {
            filter_level: None,
            filter_source: None,
            search_text: String::new(),
            auto_scroll: true,
            max_lines: 5000,
        }
    }
    
    pub fn draw_filters(&mut self, ui: &mut Ui) {
        ui.label("Filtros:");
        
        egui::ComboBox::from_id_salt("log_level_filter")
            .selected_text(match self.filter_level {
                Some(l) => format!("{:?}", l),
                None => "Todos".to_string(),
            })
            .show_ui(ui, |ui| {
                ui.selectable_value(&mut self.filter_level, None, "Todos");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Info), "Info");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Warn), "Warn");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Error), "Error");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Debug), "Debug");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Success), "Success");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Progress), "Progress");
            });
        
        egui::ComboBox::from_id_salt("log_source_filter")
            .selected_text(match self.filter_source {
                Some(s) => format!("{:?}", s),
                None => "Todas".to_string(),
            })
            .show_ui(ui, |ui| {
                ui.selectable_value(&mut self.filter_source, None, "Todas");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::Gui), "GUI");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::BackendStdout), "Backend Stdout");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::BackendStderr), "Backend Stderr");
            });
        
        ui.add(TextEdit::singleline(&mut self.search_text)
            .hint_text("🔍 Buscar...")
            .desired_width(200.0));
        
        ui.checkbox(&mut self.auto_scroll, "📜 Auto-scroll");
    }
    
    pub fn draw(&mut self, ui: &mut Ui, logs: &VecDeque<LogEntry>) {
        let available_height = ui.available_height();
        
        ScrollArea::vertical()
            .auto_shrink([false, false])
            .stick_to_bottom(self.auto_scroll)
            .max_height(available_height)
            .show_rows(ui, 18.0, logs.len(), |ui, row_range| {
                for idx in row_range.start..row_range.end {
                    if let Some(entry) = logs.get(idx) {
                        if let Some(f) = self.filter_level {
                            if entry.level != f { continue; }
                        }
                        if let Some(f) = self.filter_source {
                            if entry.source != f { continue; }
                        }
                        if !self.search_text.is_empty() {
                            if !entry.message.to_lowercase().contains(&self.search_text.to_lowercase()) {
                                continue;
                            }
                        }
                        
                        self.draw_log_entry(ui, entry);
                    }
                }
            });
    }
    
    fn draw_log_entry(&self, ui: &mut Ui, entry: &LogEntry) {
        let time_str = entry.timestamp.format("%H:%M:%S%.3f").to_string();
        
        let (level_color, level_prefix) = match entry.level {
            LogLevel::Info => (Color32::LIGHT_BLUE, "[INFO]"),
            LogLevel::Warn => (Color32::YELLOW, "[WARN]"),
            LogLevel::Error => (Color32::RED, "[ERROR]"),
            LogLevel::Debug => (Color32::GRAY, "[DEBUG]"),
            LogLevel::Success => (Color32::GREEN, "[OK]"),
            LogLevel::Progress => (Color32::from_rgb(70, 130, 180), "[PROG]"),
        };
        
        let source_str = match entry.source {
            LogSource::Gui => "GUI",
            LogSource::BackendStdout => "OUT",
            LogSource::BackendStderr => "ERR",
        };
        
        ui.horizontal(|ui| {
            ui.label(RichText::new(time_str).monospace().size(11.0).color(Color32::GRAY));
            ui.label(RichText::new(format!("{:<4}", source_str)).monospace().size(11.0).color(Color32::DARK_GRAY));
            ui.label(RichText::new(level_prefix).monospace().size(11.0).color(level_color));
            
            let msg = RichText::new(&entry.message).monospace().size(11.0);
            ui.label(msg);
        });
    }
}