//! System Optimization Toolkit — GUI Entry Point

use color_eyre::Result;
use eframe::egui;
use std::sync::Arc;
use tracing_subscriber::{EnvFilter, fmt};

mod app;
mod backend;
mod tabs;
mod widgets;

use app::SysOptApp;

fn main() -> Result<()> {
    color_eyre::install()?;

    // Setup tracing
    let file_appender = tracing_appender::rolling::daily("/tmp", "sysopt-gui.log");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);
    
    fmt()
        .with_env_filter(EnvFilter::from_default_env()
            .add_directive("sysopt_gui=debug".parse()?)
            .add_directive("eframe=warn".parse()?))
        .with_writer(non_blocking)
        .with_ansi(false)
        .init();

    let icon = load_icon();
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_min_inner_size([900.0, 600.0])
            .with_title("System Optimization Toolkit")
            .with_icon(icon.unwrap_or_default()),
        centered: true,
        persist_window: true,
        renderer: eframe::Renderer::Wgpu,
        multisampling: 4,
        depth_buffer: 0,
        stencil_buffer: 0,
        hardware_acceleration: eframe::HardwareAcceleration::Preferred,
        ..Default::default()
    };

    eframe::run_native(
        "System Optimization Toolkit",
        native_options,
        Box::new(|cc| {
            setup_fonts(&cc.egui_ctx);
            let mut app = SysOptApp::new(cc);
            app.load_persisted_state(&cc.egui_ctx);
            Ok(Box::new(app))
        }),
    ).map_err(|e| color_eyre::eyre::eyre!("eframe error: {}", e))?;

    Ok(())
}

fn load_icon() -> Option<egui::IconData> {
    // Tenta carregar ícone embedded, senão usa padrão
    if let Ok(icon_bytes) = std::fs::read("../assets/icon.png") {
        if let Ok(image) = image::load_from_memory(&icon_bytes) {
            let image = image.into_rgba8();
            let (width, height) = image.dimensions();
            return Some(egui::IconData {
                rgba: image.into_raw(),
                width,
                height,
            });
        }
    }
    None
}

fn setup_fonts(ctx: &egui::Context) {
    let mut fonts = egui::FontDefinitions::default();
    
    // Fonte monoespaçada para logs (embedded ou sistema)
    #[cfg(feature = "embedded_fonts")]
    {
        fonts.font_data.insert(
            "jetbrains_mono".to_owned(),
            egui::FontData::from_static(include_bytes!("../assets/fonts/JetBrainsMono-Regular.ttf"))
        );
        fonts.font_data.insert(
            "inter".to_owned(),
            egui::FontData::from_static(include_bytes!("../assets/fonts/Inter-Regular.ttf"))
        );
    }
    
    fonts.families.insert(
        egui::FontFamily::Monospace,
        vec!["jetbrains_mono".to_owned(), "monospace".to_owned()]
    );
    fonts.families.insert(
        egui::FontFamily::Proportional,
        vec!["inter".to_owned(), "sans-serif".to_owned()]
    );
    
    ctx.set_fonts(fonts);
}