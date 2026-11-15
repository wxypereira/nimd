//! Backend module — Core.sh runner and event handling

pub mod events;
pub mod runner;

pub use events::{BackendCommand, BackendEvent};
pub use runner::Backend;