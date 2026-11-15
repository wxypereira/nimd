//! Eventos de comunicação Backend ↔ GUI

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Comandos que a GUI envia para o Backend
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "cmd")]
pub enum BackendCommand {
    Audit { json: bool },
    Tune { apply: bool, restore: bool, dry_run: bool },
    Memory { cron: Option<String>, remove_cron: bool, dry_run: bool },
    Bench { quick: bool, output: Option<String> },
    TestSuite { 
        baseline_only: bool,
        performance_only: bool,
        memory_only: bool,
        combined_only: bool,
        quick: bool,
        no_restore: bool,
    },
    Report,
}

impl BackendCommand {
    pub fn to_args(&self) -> Vec<String> {
        let mut args = vec![];
        
        match self {
            BackendCommand::Audit { json } => {
                args.push("audit".to_string());
                if *json { args.push("--json".to_string()); }
            }
            BackendCommand::Tune { apply, restore, dry_run } => {
                args.push("tune".to_string());
                if *apply { args.push("--apply".to_string()); }
                if *restore { args.push("--restore".to_string()); }
                if *dry_run { args.push("--dry-run".to_string()); }
            }
            BackendCommand::Memory { cron, remove_cron, dry_run } => {
                args.push("memory".to_string());
                if let Some(c) = cron { 
                    args.push("--cron".to_string()); 
                    args.push(c.clone()); 
                }
                if *remove_cron { args.push("--remove-cron".to_string()); }
                if *dry_run { args.push("--dry-run".to_string()); }
            }
            BackendCommand::Bench { quick, output } => {
                args.push("bench".to_string());
                if *quick { args.push("--quick".to_string()); }
                if let Some(o) = output { 
                    args.push("--output".to_string()); 
                    args.push(o.clone()); 
                }
            }
            BackendCommand::TestSuite { 
                baseline_only, performance_only, memory_only, combined_only, 
                quick, no_restore 
            } => {
                args.push("test-suite".to_string());
                if *baseline_only { args.push("--baseline-only".to_string()); }
                if *performance_only { args.push("--performance-only".to_string()); }
                if *memory_only { args.push("--memory-only".to_string()); }
                if *combined_only { args.push("--combined-only".to_string()); }
                if *quick { args.push("--quick".to_string()); }
                if *no_restore { args.push("--no-restore".to_string()); }
            }
            BackendCommand::Report => {
                args.push("report".to_string());
            }
        }
        
        args
    }
}

/// Eventos que o Backend envia para a GUI
#[derive(Debug, Clone)]
pub enum BackendEvent {
    Progress {
        stage: String,
        current: u32,
        total: u32,
        percent: u32,
        message: String,
    },
    Result {
        section: String,
        data: Value,
    },
    Log {
        level: String,
        message: String,
    },
    Complete {
        exit_code: i32,
        duration_ms: u64,
        message: String,
    },
    Error {
        message: String,
    },
}