//! WebSocket frame parsing and encoding.
//!
//! This module implements RFC 6455 frame format parsing with support for:
//! - All standard opcodes (text, binary, close, ping, pong, continuation)
//! - Frame masking (required for client-to-server messages)
//! - Fragmented messages
//! - Control frame validation

use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::errors::ProtocolError;
use crate::mask::{apply_mask_inplace, generate_mask};

/// WebSocket frame opcodes.
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Opcode {
    Continuation = 0x0,
    Text = 0x1,
    Binary = 0x2,
    Close = 0x8,
    Ping = 0x9,
    Pong = 0xA,
}

impl Opcode {
    /// Parse opcode from a byte value.
    pub fn from_u8(value: u8) -> Result<Self, ProtocolError> {
        match value {
            0x0 => Ok(Opcode::Continuation),
            0x1 => Ok(Opcode::Text),
            0x2 => Ok(Opcode::Binary),
            0x8 => Ok(Opcode::Close),
            0x9 => Ok(Opcode::Ping),
            0xA => Ok(Opcode::Pong),
            _ => Err(ProtocolError::InvalidOpcode(value)),
        }
    }

    /// Check if this is a control opcode.
    #[inline]
    pub fn is_control(&self) -> bool {
        matches!(self, Opcode::Close | Opcode::Ping | Opcode::Pong)
    }
}

#[pymethods]
impl Opcode {
    /// Check if this is a control frame opcode.
    #[getter]
    fn is_control_frame(&self) -> bool {
        self.is_control()
    }

    /// Check if this is a data frame opcode.
    #[getter]
    fn is_data_frame(&self) -> bool {
        !self.is_control()
    }
}

/// A parsed WebSocket frame.
#[pyclass(name = "Frame")]
#[derive(Clone, Debug)]
pub struct PyFrame {
    #[pyo3(get)]
    pub opcode: Opcode,
    #[pyo3(get)]
    pub fin: bool,
    #[pyo3(get)]
    pub rsv1: bool,
    #[pyo3(get)]
    pub rsv2: bool,
    #[pyo3(get)]
    pub rsv3: bool,
    payload: Vec<u8>,
}

#[pymethods]
impl PyFrame {
    /// Get the frame payload as bytes.
    #[getter]
    fn payload<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.payload)
    }

    /// Get payload length.
    #[getter]
    fn payload_len(&self) -> usize {
        self.payload.len()
    }

    /// Decode payload as UTF-8 text (SIMD-accelerated validation).
    fn as_text(&self) -> PyResult<String> {
        // Use simdutf8 for fast validation, then convert without re-validating
        simdutf8::basic::from_utf8(&self.payload)
            .map(|s| s.to_string())
            .map_err(|_| ProtocolError::InvalidUtf8.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "Frame(opcode={:?}, fin={}, payload_len={})",
            self.opcode,
            self.fin,
            self.payload.len()
        )
    }
}

/// WebSocket frame parser with configurable limits.
///
/// This parser follows the sans-I/O pattern: it accepts raw bytes and returns
/// parsed frames without performing any I/O operations.
#[pyclass]
pub struct FrameParser {
    max_frame_size: usize,
    max_message_size: usize,
    buffer: Vec<u8>,
    // For message assembly from fragments
    message_buffer: Vec<u8>,
    message_opcode: Option<Opcode>,
}

#[pymethods]
impl FrameParser {
    /// Create a new frame parser with configurable limits.
    ///
    /// Args:
    ///     max_frame_size: Maximum size of a single frame (default: 16MB)
    ///     max_message_size: Maximum size of an assembled message (default: 64MB)
    #[new]
    #[pyo3(signature = (max_frame_size=16*1024*1024, max_message_size=64*1024*1024))]
    pub fn new(max_frame_size: usize, max_message_size: usize) -> Self {
        Self {
            max_frame_size,
            max_message_size,
            buffer: Vec::with_capacity(4096),
            message_buffer: Vec::new(),
            message_opcode: None,
        }
    }

    /// Feed raw bytes into the parser.
    ///
    /// Returns a tuple of (frames, bytes_consumed) where frames is a list of
    /// complete frames that could be parsed from the input.
    pub fn feed(&mut self, data: &[u8]) -> PyResult<(Vec<PyFrame>, usize)> {
        self.buffer.extend_from_slice(data);
        let mut frames = Vec::new();
        let mut total_consumed = 0;

        loop {
            match self.parse_frame() {
                Ok(Some((frame, consumed))) => {
                    total_consumed += consumed;
                    frames.push(frame);
                    // Remove consumed bytes immediately to avoid re-parsing
                    self.buffer.drain(..consumed);
                }
                Ok(None) => break, // Need more data
                Err(e) => return Err(e.into()),
            }
        }

        Ok((frames, total_consumed))
    }

    /// Encode a frame for sending.
    ///
    /// Args:
    ///     opcode: The frame opcode
    ///     payload: The payload bytes
    ///     mask: Whether to mask the frame (required for client-to-server)
    ///     fin: Whether this is the final fragment
    #[pyo3(signature = (opcode, payload, mask=true, fin=true, rsv1=false))]
    pub fn encode<'py>(
        &mut self,
        py: Python<'py>,
        opcode: u8,
        payload: &[u8],
        mask: bool,
        fin: bool,
        rsv1: bool,
    ) -> PyResult<Bound<'py, PyBytes>> {
        let opcode = Opcode::from_u8(opcode)?;
        let total_size = Self::compute_frame_size(payload.len(), mask);

        // Zero-copy: write frame directly into Python bytes allocation
        PyBytes::new_bound_with(py, total_size, |buf| {
            Self::write_frame_into(buf, opcode, payload, mask, fin, rsv1);
            Ok(())
        })
    }

    /// Build a close frame with code and reason.
    #[pyo3(signature = (code=1000, reason="", mask=true))]
    pub fn encode_close<'py>(
        &mut self,
        py: Python<'py>,
        code: u16,
        reason: &str,
        mask: bool,
    ) -> PyResult<Bound<'py, PyBytes>> {
        // Build close payload: 2-byte code + reason
        let reason_bytes = reason.as_bytes();
        let close_payload_len = 2 + reason_bytes.len();
        let total_size = Self::compute_frame_size(close_payload_len, mask);

        PyBytes::new_bound_with(py, total_size, |buf| {
            // Assemble close payload inline
            let mut close_payload = Vec::with_capacity(close_payload_len);
            close_payload.extend_from_slice(&code.to_be_bytes());
            close_payload.extend_from_slice(reason_bytes);
            Self::write_frame_into(buf, Opcode::Close, &close_payload, mask, true, false);
            Ok(())
        })
    }

    /// Reset parser state (for reconnection).
    pub fn reset(&mut self) {
        self.buffer.clear();
        self.message_buffer.clear();
        self.message_opcode = None;
    }
}

impl FrameParser {
    /// Parse a single frame from the buffer.
    fn parse_frame(&mut self) -> Result<Option<(PyFrame, usize)>, ProtocolError> {
        if self.buffer.len() < 2 {
            return Ok(None);
        }

        let first_byte = self.buffer[0];
        let second_byte = self.buffer[1];

        // Parse first byte
        let fin = (first_byte & 0x80) != 0;
        let rsv1 = (first_byte & 0x40) != 0;
        let rsv2 = (first_byte & 0x20) != 0;
        let rsv3 = (first_byte & 0x10) != 0;
        let opcode = Opcode::from_u8(first_byte & 0x0F)?;

        // Check reserved bits (should be 0 unless extension negotiated)
        // RSV1 is used for permessage-deflate, we'll allow it
        if rsv2 || rsv3 {
            return Err(ProtocolError::ReservedBitsSet);
        }

        // Parse second byte
        let masked = (second_byte & 0x80) != 0;
        let payload_len_byte = second_byte & 0x7F;

        // Calculate header size and payload length
        let (header_size, payload_len) = self.parse_length(payload_len_byte, masked)?;

        // Check frame size limit
        if payload_len > self.max_frame_size {
            return Err(ProtocolError::FrameTooLarge {
                size: payload_len,
                max: self.max_frame_size,
            });
        }

        // Control frame validation
        if opcode.is_control() {
            if payload_len > 125 {
                return Err(ProtocolError::ControlFrameTooLarge(payload_len));
            }
            if !fin {
                return Err(ProtocolError::FragmentedControlFrame);
            }
        }

        // Check if we have enough data
        let total_size = header_size + payload_len;
        if self.buffer.len() < total_size {
            return Ok(None);
        }

        // Extract mask key if present
        let mask_key = if masked {
            let mask_offset = header_size - 4;
            Some([
                self.buffer[mask_offset],
                self.buffer[mask_offset + 1],
                self.buffer[mask_offset + 2],
                self.buffer[mask_offset + 3],
            ])
        } else {
            None
        };

        // Extract and unmask payload
        let mut payload = self.buffer[header_size..total_size].to_vec();
        if let Some(mask) = mask_key {
            apply_mask_inplace(&mut payload, mask);
        }

        let frame = PyFrame {
            opcode,
            fin,
            rsv1,
            rsv2,
            rsv3,
            payload,
        };

        Ok(Some((frame, total_size)))
    }

    /// Parse the payload length from the header.
    fn parse_length(
        &self,
        initial_len: u8,
        masked: bool,
    ) -> Result<(usize, usize), ProtocolError> {
        let mask_size = if masked { 4 } else { 0 };

        match initial_len {
            0..=125 => Ok((2 + mask_size, initial_len as usize)),
            126 => {
                if self.buffer.len() < 4 {
                    return Err(ProtocolError::IncompleteFrame { needed: 4 - self.buffer.len() });
                }
                let len = u16::from_be_bytes([self.buffer[2], self.buffer[3]]) as usize;
                Ok((4 + mask_size, len))
            }
            127 => {
                if self.buffer.len() < 10 {
                    return Err(ProtocolError::IncompleteFrame { needed: 10 - self.buffer.len() });
                }
                let len = u64::from_be_bytes([
                    self.buffer[2], self.buffer[3], self.buffer[4], self.buffer[5],
                    self.buffer[6], self.buffer[7], self.buffer[8], self.buffer[9],
                ]) as usize;
                Ok((10 + mask_size, len))
            }
            _ => unreachable!(),
        }
    }

    /// Compute the total encoded frame size.
    #[inline]
    fn compute_frame_size(payload_len: usize, mask: bool) -> usize {
        let len_bytes = if payload_len <= 125 {
            1
        } else if payload_len <= 65535 {
            3
        } else {
            9
        };
        let mask_size = if mask { 4 } else { 0 };
        1 + len_bytes + mask_size + payload_len
    }

    /// Write a complete frame into a pre-allocated buffer.
    /// Buffer must be exactly `compute_frame_size()` bytes.
    fn write_frame_into(
        buf: &mut [u8],
        opcode: Opcode,
        payload: &[u8],
        mask: bool,
        fin: bool,
        rsv1: bool,
    ) {
        let payload_len = payload.len();
        let mut pos = 0;

        // First byte: FIN + RSV1 + opcode
        let mut first_byte = if fin { 0x80 } else { 0x00 } | (opcode as u8);
        if rsv1 {
            first_byte |= 0x40;
        }
        buf[pos] = first_byte;
        pos += 1;

        // Second byte and extended length
        let mask_bit = if mask { 0x80 } else { 0x00 };
        if payload_len <= 125 {
            buf[pos] = mask_bit | (payload_len as u8);
            pos += 1;
        } else if payload_len <= 65535 {
            buf[pos] = mask_bit | 126;
            pos += 1;
            buf[pos..pos + 2].copy_from_slice(&(payload_len as u16).to_be_bytes());
            pos += 2;
        } else {
            buf[pos] = mask_bit | 127;
            pos += 1;
            buf[pos..pos + 8].copy_from_slice(&(payload_len as u64).to_be_bytes());
            pos += 8;
        }

        // Mask key and payload
        if mask {
            let mask_key = generate_mask();
            buf[pos..pos + 4].copy_from_slice(&mask_key);
            pos += 4;
            buf[pos..pos + payload_len].copy_from_slice(payload);
            apply_mask_inplace(&mut buf[pos..pos + payload_len], mask_key);
        } else {
            buf[pos..pos + payload_len].copy_from_slice(payload);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_text_frame() {
        let mut parser = FrameParser::new(1024, 4096);
        // Unmasked text frame with "Hello"
        let frame_data = [
            0x81, 0x05,  // FIN=1, opcode=1 (text), len=5
            b'H', b'e', b'l', b'l', b'o',
        ];

        let (frames, consumed) = parser.feed(&frame_data).unwrap();
        assert_eq!(consumed, 7);
        assert_eq!(frames.len(), 1);
        assert!(frames[0].fin);
        assert_eq!(frames[0].opcode, Opcode::Text);
        assert_eq!(frames[0].payload, b"Hello");
    }

    #[test]
    fn test_parse_masked_frame() {
        let mut parser = FrameParser::new(1024, 4096);
        // Masked text frame with "Hello"
        let mask = [0x37, 0xfa, 0x21, 0x3d];
        let mut payload = *b"Hello";
        for (i, byte) in payload.iter_mut().enumerate() {
            *byte ^= mask[i % 4];
        }

        let mut frame_data = vec![
            0x81, 0x85,  // FIN=1, opcode=1, MASK=1, len=5
        ];
        frame_data.extend_from_slice(&mask);
        frame_data.extend_from_slice(&payload);

        let (frames, _) = parser.feed(&frame_data).unwrap();
        assert_eq!(frames.len(), 1);
        assert_eq!(frames[0].payload, b"Hello");
    }

    #[test]
    fn test_encode_decode_roundtrip() {
        let parser = FrameParser::new(1024, 4096);
        let original = b"Test message";

        Python::with_gil(|py| {
            let encoded = parser.encode(py, Opcode::Text as u8, original, true, true).unwrap();
            let encoded_bytes = encoded.as_bytes();

            let mut parser2 = FrameParser::new(1024, 4096);
            let (frames, _) = parser2.feed(encoded_bytes).unwrap();

            assert_eq!(frames.len(), 1);
            assert_eq!(frames[0].payload, original);
        });
    }

    #[test]
    fn test_binary_frame() {
        let mut parser = FrameParser::new(1024, 4096);
        let frame_data = [
            0x82, 0x04,  // FIN=1, opcode=2 (binary), len=4
            0x00, 0x01, 0x02, 0x03,
        ];

        let (frames, _) = parser.feed(&frame_data).unwrap();
        assert_eq!(frames[0].opcode, Opcode::Binary);
        assert_eq!(frames[0].payload, &[0x00, 0x01, 0x02, 0x03]);
    }

    #[test]
    fn test_control_frame_too_large() {
        let mut parser = FrameParser::new(1024, 4096);
        // Ping frame claiming 126 bytes (invalid)
        let frame_data = [0x89, 0x7E, 0x00, 0x7E];  // len=126

        let result = parser.feed(&frame_data);
        assert!(result.is_err());
    }
}
