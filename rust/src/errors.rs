//! Error types for the WSFabric Rust core.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use thiserror::Error;

/// Protocol errors that can occur during frame parsing.
#[derive(Error, Debug)]
pub enum ProtocolError {
    #[error("Invalid opcode: {0}")]
    InvalidOpcode(u8),

    #[error("Invalid frame: {0}")]
    InvalidFrame(String),

    #[error("Frame too large: {size} bytes (max: {max})")]
    FrameTooLarge { size: usize, max: usize },

    #[error("Invalid UTF-8 in text frame")]
    InvalidUtf8,

    #[error("Control frame too large: {0} bytes (max: 125)")]
    ControlFrameTooLarge(usize),

    #[error("Fragmented control frame")]
    FragmentedControlFrame,

    #[error("Invalid close code: {0}")]
    InvalidCloseCode(u16),

    #[error("Unexpected continuation frame")]
    UnexpectedContinuation,

    #[error("Expected continuation frame")]
    ExpectedContinuation,

    #[error("Reserved bits set without extension")]
    ReservedBitsSet,

    #[error("Incomplete frame: need {needed} more bytes")]
    IncompleteFrame { needed: usize },
}

impl From<ProtocolError> for PyErr {
    fn from(err: ProtocolError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

/// Handshake errors.
#[derive(Error, Debug)]
pub enum HandshakeError {
    #[error("Invalid HTTP response")]
    InvalidResponse,

    #[error("HTTP {status}: {reason}")]
    HttpError { status: u16, reason: String },

    #[error("Invalid Sec-WebSocket-Accept")]
    InvalidAccept,

    #[error("Missing required header: {0}")]
    MissingHeader(String),
}

impl From<HandshakeError> for PyErr {
    fn from(err: HandshakeError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}
