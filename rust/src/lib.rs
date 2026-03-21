//! WSFabric Core - Rust-powered WebSocket primitives.
//!
//! This crate provides high-performance WebSocket frame parsing, masking,
//! and compression for the WSFabric Python library.

mod errors;
mod frame;
mod handshake;
mod mask;

use pyo3::prelude::*;

/// WSFabric Rust core module.
///
/// Exposes frame parsing, masking, and handshake utilities to Python.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<frame::FrameParser>()?;
    m.add_class::<frame::PyFrame>()?;
    m.add_class::<frame::Opcode>()?;
    m.add_class::<handshake::Handshake>()?;
    m.add_function(wrap_pyfunction!(mask::apply_mask, m)?)?;
    m.add_function(wrap_pyfunction!(handshake::generate_key, m)?)?;
    m.add_function(wrap_pyfunction!(handshake::validate_accept, m)?)?;
    Ok(())
}
