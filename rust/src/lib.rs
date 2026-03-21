//! WSFabric Core - Rust-powered WebSocket primitives.
//!
//! This crate provides high-performance WebSocket frame parsing, masking,
//! compression, and message buffering for the WSFabric Python library.

mod buffer;
mod errors;
mod frame;
mod handshake;
mod mask;

use pyo3::prelude::*;

/// WSFabric Rust core module.
///
/// Exposes frame parsing, masking, handshake utilities, and ring buffer to Python.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Frame parsing
    m.add_class::<frame::FrameParser>()?;
    m.add_class::<frame::PyFrame>()?;
    m.add_class::<frame::Opcode>()?;

    // Handshake
    m.add_class::<handshake::Handshake>()?;
    m.add_function(wrap_pyfunction!(handshake::generate_key, m)?)?;
    m.add_function(wrap_pyfunction!(handshake::validate_accept, m)?)?;

    // Masking
    m.add_function(wrap_pyfunction!(mask::apply_mask, m)?)?;

    // Buffer
    m.add_class::<buffer::RingBuffer>()?;
    m.add_class::<buffer::OverflowPolicy>()?;

    Ok(())
}
