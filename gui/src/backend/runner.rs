//! Backend Runner — Executa core.sh em background com streaming de stdout/stderr

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;
use std::time::Duration;

use anyhow::Result;
use crossbeam_channel::{Sender, Receiver, unbounded};
use serde_json::Value;
use tokio::process::Command as AsyncCommand;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::sync::mpsc;
use tracing::{info};

use super::events::{BackendEvent, BackendCommand};
use crate::app::LogEntry;

/// Runner do backend — gerencia processo core.sh
pub struct Backend {
    core_path: PathBuf,
    event_tx: Sender<BackendEvent>,
    event_rx: Receiver<BackendEvent>,
    global_logs: Arc<Mutex<VecDeque<LogEntry>>>,
    current_child: Arc<Mutex<Option<tokio::process::Child>>>,
    cmd_tx: mpsc::UnboundedSender<BackendCommand>,
    cmd_rx: Arc<Mutex<Option<mpsc::UnboundedReceiver<BackendCommand>>>>,
    poll_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

impl Backend {
    pub fn new(
        core_path: impl Into<PathBuf>,
        event_tx: Sender<BackendEvent>,
        global_logs: Arc<Mutex<VecDeque<LogEntry>>>,
    ) -> Self {
        let (cmd_tx, cmd_rx) = mpsc::unbounded_channel();
        let (event_tx2, event_rx) = unbounded();
        
        Self {
            core_path: core_path.into(),
            event_tx: event_tx2,
            event_rx,
            global_logs,
            current_child: Arc::new(Mutex::new(None)),
            cmd_tx,
            cmd_rx: Arc::new(Mutex::new(Some(cmd_rx))),
            poll_handle: Arc::new(Mutex::new(None)),
        }
    }
    
    pub fn core_path(&self) -> &PathBuf {
        &self.core_path
    }
    
    pub fn try_recv_event(&self) -> Result<BackendEvent, crossbeam_channel::TryRecvError> {
        self.event_rx.try_recv()
    }
    
    pub fn execute(&self, command: BackendCommand) -> Result<()> {
        self.cmd_tx.send(command)?;
        Ok(())
    }
    
    pub fn poll(&self) {
        // Processa comandos pendentes
        if let Ok(mut rx_guard) = self.cmd_rx.lock() {
            if let Some(rx) = rx_guard.as_mut() {
                while let Ok(cmd) = rx.try_recv() {
                    self.spawn_command(cmd);
                }
            }
        }
    }
    
    fn spawn_command(&self, cmd: BackendCommand) {
        let core_path = self.core_path.clone();
        let event_tx = self.event_tx.clone();
        let global_logs = self.global_logs.clone();
        let current_child = self.current_child.clone();
        
        let handle = tokio::spawn(async move {
            let args = cmd.to_args();
            
            info!("Executando: {} {}", core_path.display(), args.join(" "));
            
            let mut child = match AsyncCommand::new(&core_path)
                .args(&args)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    let _ = event_tx.send(BackendEvent::Error {
                        message: format!("Falha ao iniciar core.sh: {}", e),
                    });
                    return;
                }
            };
            
            // Pega stdout/stderr ANTES de mover child
            let stdout = child.stdout.take().expect("stdout piped");
            let stderr = child.stderr.take().expect("stderr piped");
            
            *current_child.lock().unwrap() = Some(child);
            
            let event_tx_stdout = event_tx.clone();
            let event_tx_stderr = event_tx.clone();
            
            // Task para ler stdout (JSON Lines)
            let stdout_handle = tokio::spawn(async move {
                let mut reader = BufReader::new(stdout).lines();
                while let Ok(Some(line)) = reader.next_line().await {
                    let line_str = line;
                    if let Ok(json) = serde_json::from_str::<Value>(&line_str) {
                        if let Some(event) = parse_json_event(json) {
                            let _ = event_tx_stdout.send(event);
                        }
                    } else {
                        let _ = event_tx_stdout.send(BackendEvent::Log {
                            level: "INFO".to_string(),
                            message: line_str,
                        });
                    }
                }
            });
            
            // Task para ler stderr (logs humanos)
            let stderr_handle = tokio::spawn(async move {
                let mut reader = BufReader::new(stderr).lines();
                while let Ok(Some(line)) = reader.next_line().await {
                    let line_str = line;
                    let (level, msg) = parse_log_line(&line_str);
                    let _ = event_tx_stderr.send(BackendEvent::Log {
                        level,
                        message: msg,
                    });
                }
            });
            
            // Aguarda conclusão - pega o child do lock sem manter o guard durante await
            let exit_status = {
                let mut child_guard = current_child.lock().unwrap();
                child_guard.take()
            };
            
            let exit_status = match exit_status {
                Some(mut child) => child.wait().await,
                None => Err(std::io::Error::new(std::io::ErrorKind::Other, "Child already taken")),
            };
            
            let _ = tokio::join!(stdout_handle, stderr_handle);
            
            let (exit_code, duration_ms) = match exit_status {
                Ok(status) => (status.code().unwrap_or(-1), 0),
                Err(e) => {
                    let _ = event_tx.send(BackendEvent::Error {
                        message: format!("Erro no processo: {}", e),
                    });
                    return;
                }
            };
            
            let _ = event_tx.send(BackendEvent::Complete {
                exit_code,
                duration_ms,
                message: if exit_code == 0 { "Sucesso".to_string() } else { "Falha".to_string() },
            });
        });
        
        *self.poll_handle.lock().unwrap() = Some(handle);
    }
    
    pub fn shutdown(&self) {
        if let Ok(mut child_guard) = self.current_child.lock() {
            if let Some(mut child) = child_guard.take() {
                info!("Enviando SIGTERM para processo core.sh");
                let _ = child.start_kill();
                
                tokio::spawn(async move {
                    tokio::time::sleep(Duration::from_secs(2)).await;
                    let _ = child.kill().await;
                });
            }
        }
    }
}

fn parse_log_line(line: &str) -> (String, String) {
    if let Some(end_bracket) = line.find(']') {
        if line.starts_with('[') {
            let level = line[1..end_bracket].trim().to_string();
            let message = line[end_bracket + 1..].trim().to_string();
            return (level, message);
        }
    }
    ("INFO".to_string(), line.to_string())
}

fn parse_json_event(json: Value) -> Option<BackendEvent> {
    let event_type = json.get("type")?.as_str()?;
    
    match event_type {
        "progress" => Some(BackendEvent::Progress {
            stage: json.get("stage")?.as_str()?.to_string(),
            current: json.get("current")?.as_u64()? as u32,
            total: json.get("total")?.as_u64()? as u32,
            percent: json.get("percent")?.as_u64()? as u32,
            message: json.get("message")?.as_str().unwrap_or("").to_string(),
        }),
        "result" => Some(BackendEvent::Result {
            section: json.get("section")?.as_str()?.to_string(),
            data: json.get("data")?.clone(),
        }),
        "complete" => Some(BackendEvent::Complete {
            exit_code: json.get("exit_code")?.as_i64()? as i32,
            duration_ms: json.get("duration_ms")?.as_u64()? as u64,
            message: json.get("message")?.as_str().unwrap_or("").to_string(),
        }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_log_line() {
        assert_eq!(parse_log_line("[INFO] Hello"), ("INFO".to_string(), "Hello".to_string()));
        assert_eq!(parse_log_line("[WARN] Warning msg"), ("WARN".to_string(), "Warning msg".to_string()));
        assert_eq!(parse_log_line("No bracket"), ("INFO".to_string(), "No bracket".to_string()));
    }
    
    #[test]
    fn test_backend_command_to_args() {
        let cmd = BackendCommand::Audit { json: true };
        assert_eq!(cmd.to_args(), vec!["audit", "--json"]);
        
        let cmd = BackendCommand::Tune { apply: true, restore: false, dry_run: true };
        assert_eq!(cmd.to_args(), vec!["tune", "--apply", "--dry-run"]);
    }
}