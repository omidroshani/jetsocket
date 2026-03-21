//! WSFabric Core - Rust-powered WebSocket primitives.
//!
//! This crate provides high-performance WebSocket frame parsing, masking,
//! compression, and message buffering for the WSFabric Python library.

mod buffer;
mod compress;
mod errors;
mod frame;
mod handshake;
mod mask;

use pyo3::prelude::*;

/// SIMD-accelerated UTF-8 validation.
///
/// Returns True if the data is valid UTF-8, False otherwise.
/// Uses simdutf8 for hardware-accelerated validation on supported platforms.
#[pyfunction]
fn validate_utf8(data: &[u8]) -> bool {
    simdutf8::basic::from_utf8(data).is_ok()
}

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

    // Compression
    m.add_class::<compress::Deflater>()?;
    m.add_function(wrap_pyfunction!(compress::parse_deflate_params, m)?)?;

    // UTF-8 validation
    m.add_function(wrap_pyfunction!(validate_utf8, m)?)?;

    // Buffer
    m.add_class::<buffer::RingBuffer>()?;
    m.add_class::<buffer::OverflowPolicy>()?;

    Ok(())
}
