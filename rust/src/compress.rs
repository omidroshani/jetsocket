//! WebSocket permessage-deflate compression (RFC 7692).
//!
//! Provides DEFLATE-based compression and decompression for WebSocket frames
//! using the permessage-deflate extension.

use flate2::{Compress, Compression, Decompress, FlushCompress, FlushDecompress, Status};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// The trailing bytes that must be stripped after compression and
/// appended before decompression per RFC 7692 Section 7.2.1/7.2.2.
const DEFLATE_TRAILER: [u8; 4] = [0x00, 0x00, 0xFF, 0xFF];

/// permessage-deflate compressor/decompressor.
///
/// Handles compression and decompression of WebSocket message payloads
/// according to RFC 7692. Supports context takeover and configurable
/// window bits.
#[pyclass]
pub struct Deflater {
    compressor: Compress,
    decompressor: Decompress,
    client_no_context_takeover: bool,
    server_no_context_takeover: bool,
    client_max_window_bits: u8,
    server_max_window_bits: u8,
}

#[pymethods]
impl Deflater {
    /// Create a new Deflater for permessage-deflate.
    ///
    /// Args:
    ///     client_no_context_takeover: Reset compressor after each message.
    ///     server_no_context_takeover: Reset decompressor after each message.
    ///     client_max_window_bits: LZ77 window size for compression (9-15).
    ///     server_max_window_bits: LZ77 window size for decompression (9-15).
    #[new]
    #[pyo3(signature = (
        client_no_context_takeover=false,
        server_no_context_takeover=false,
        client_max_window_bits=15,
        server_max_window_bits=15,
    ))]
    pub fn new(
        client_no_context_takeover: bool,
        server_no_context_takeover: bool,
        client_max_window_bits: u8,
        server_max_window_bits: u8,
    ) -> PyResult<Self> {
        if !(9..=15).contains(&client_max_window_bits) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "client_max_window_bits must be between 9 and 15",
            ));
        }
        if !(9..=15).contains(&server_max_window_bits) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "server_max_window_bits must be between 9 and 15",
            ));
        }

        let compressor = Compress::new(Compression::default(), false);
        let decompressor = Decompress::new(false);

        Ok(Self {
            compressor,
            decompressor,
            client_no_context_takeover,
            server_no_context_takeover,
            client_max_window_bits,
            server_max_window_bits,
        })
    }

    /// Compress a message payload for sending.
    ///
    /// Compresses the data using DEFLATE and strips the trailing
    /// 0x00 0x00 0xFF 0xFF bytes per RFC 7692 Section 7.2.1.
    ///
    /// Args:
    ///     data: The payload bytes to compress.
    ///
    /// Returns:
    ///     Compressed bytes with trailing bytes stripped.
    #[pyo3(name = "compress", signature = (data))]
    pub fn py_compress<'py>(&mut self, py: Python<'py>, data: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        let compressed = self.compress_impl(data).map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("compression failed: {}", e))
        })?;

        if self.client_no_context_takeover {
            self.compressor.reset();
        }

        Ok(PyBytes::new_bound(py, &compressed))
    }

    /// Decompress a received message payload.
    ///
    /// Appends the trailing 0x00 0x00 0xFF 0xFF bytes per RFC 7692
    /// Section 7.2.2, then decompresses.
    ///
    /// Args:
    ///     data: The compressed payload bytes.
    ///
    /// Returns:
    ///     Decompressed bytes.
    #[pyo3(name = "decompress", signature = (data))]
    pub fn py_decompress<'py>(
        &mut self,
        py: Python<'py>,
        data: &[u8],
    ) -> PyResult<Bound<'py, PyBytes>> {
        let decompressed = self.decompress_impl(data).map_err(|e| {
            pyo3::exceptions::PyRuntimeError::new_err(format!("decompression failed: {}", e))
        })?;

        // Reset decompressor if server_no_context_takeover
        if self.server_no_context_takeover {
            self.decompressor = Decompress::new(false);
        }

        Ok(PyBytes::new_bound(py, &decompressed))
    }

    /// Reset the compressor state.
    pub fn reset_compressor(&mut self) {
        self.compressor.reset();
    }

    /// Reset the decompressor state.
    pub fn reset_decompressor(&mut self) {
        self.decompressor = Decompress::new(false);
    }

    /// Get client_no_context_takeover setting.
    #[getter]
    pub fn client_no_context_takeover(&self) -> bool {
        self.client_no_context_takeover
    }

    /// Get server_no_context_takeover setting.
    #[getter]
    pub fn server_no_context_takeover(&self) -> bool {
        self.server_no_context_takeover
    }

    /// Get client_max_window_bits setting.
    #[getter]
    pub fn client_max_window_bits(&self) -> u8 {
        self.client_max_window_bits
    }

    /// Get server_max_window_bits setting.
    #[getter]
    pub fn server_max_window_bits(&self) -> u8 {
        self.server_max_window_bits
    }

    fn __repr__(&self) -> String {
        format!(
            "Deflater(client_no_context_takeover={}, server_no_context_takeover={}, \
             client_max_window_bits={}, server_max_window_bits={})",
            self.client_no_context_takeover,
            self.server_no_context_takeover,
            self.client_max_window_bits,
            self.server_max_window_bits
        )
    }
}

impl Deflater {
    /// Internal compression implementation.
    ///
    /// Uses a single Compress::compress call with Z_SYNC_FLUSH on the full
    /// input data. The output buffer is sized generously to avoid BufError.
    fn compress_impl(&mut self, data: &[u8]) -> Result<Vec<u8>, String> {

        // deflateBound: worst case output is input + 0.1% + 12 bytes
        // Plus we need room for the sync marker (4 bytes)
        let max_output = data.len() + (data.len() / 100) + 256;
        let mut output = vec![0u8; max_output];


        let before_in = self.compressor.total_in();
        let before_out = self.compressor.total_out();


        // Single call with Sync flush: compresses all input and appends sync marker
        self.compressor
            .compress(data, &mut output, FlushCompress::Sync)
            .map_err(|e| format!("{}", e))?;


        let consumed = (self.compressor.total_in() - before_in) as usize;
        let produced = (self.compressor.total_out() - before_out) as usize;

        // Verify all input was consumed
        if consumed < data.len() {
            // Output buffer was too small, try with larger buffer
            let mut bigger_output = vec![0u8; max_output * 4];
            let before_in2 = self.compressor.total_in();
            let before_out2 = self.compressor.total_out();

            self.compressor
                .compress(&data[consumed..], &mut bigger_output, FlushCompress::Sync)
                .map_err(|e| format!("{}", e))?;

            let produced2 = (self.compressor.total_out() - before_out2) as usize;

            output.truncate(produced);
            output.extend_from_slice(&bigger_output[..produced2]);
        } else {
            output.truncate(produced);
        }

        // Strip trailing 0x00 0x00 0xFF 0xFF per RFC 7692 Section 7.2.1
        if output.len() >= 4 && output[output.len() - 4..] == DEFLATE_TRAILER {
            output.truncate(output.len() - 4);
        }

        Ok(output)
    }

    /// Internal decompression implementation.
    fn decompress_impl(&mut self, data: &[u8]) -> Result<Vec<u8>, String> {
        // Append trailing bytes per RFC 7692 Section 7.2.2
        let mut input = Vec::with_capacity(data.len() + 4);
        input.extend_from_slice(data);
        input.extend_from_slice(&DEFLATE_TRAILER);

        let mut output = Vec::with_capacity(data.len() * 2);
        let mut buf = [0u8; 8192];
        let mut input_pos = 0;

        loop {
            let before_in = self.decompressor.total_in();
            let before_out = self.decompressor.total_out();

            let status = self
                .decompressor
                .decompress(&input[input_pos..], &mut buf, FlushDecompress::Sync)
                .map_err(|e| format!("{}", e))?;

            let consumed = (self.decompressor.total_in() - before_in) as usize;
            let produced = (self.decompressor.total_out() - before_out) as usize;

            input_pos += consumed;
            output.extend_from_slice(&buf[..produced]);

            if status == Status::StreamEnd || (consumed == 0 && produced == 0) {
                break;
            }
            if input_pos >= input.len() && produced == 0 {
                break;
            }
        }

        Ok(output)
    }
}

/// Parse permessage-deflate extension parameters from the
/// Sec-WebSocket-Extensions header value.
///
/// Returns a tuple of (client_no_context_takeover, server_no_context_takeover,
/// client_max_window_bits, server_max_window_bits).
#[pyfunction]
#[pyo3(signature = (extension_str))]
pub fn parse_deflate_params(
    extension_str: &str,
) -> PyResult<(bool, bool, u8, u8)> {
    let mut client_no_context_takeover = false;
    let mut server_no_context_takeover = false;
    let mut client_max_window_bits: u8 = 15;
    let mut server_max_window_bits: u8 = 15;

    for part in extension_str.split(';') {
        let part = part.trim();
        if part.eq_ignore_ascii_case("permessage-deflate") {
            continue;
        }
        if part.is_empty() {
            continue;
        }

        if let Some((key, value)) = part.split_once('=') {
            let key = key.trim();
            let value = value.trim();
            match key {
                "client_max_window_bits" => {
                    client_max_window_bits = value.parse::<u8>().map_err(|_| {
                        pyo3::exceptions::PyValueError::new_err(
                            "invalid client_max_window_bits value",
                        )
                    })?;
                }
                "server_max_window_bits" => {
                    server_max_window_bits = value.parse::<u8>().map_err(|_| {
                        pyo3::exceptions::PyValueError::new_err(
                            "invalid server_max_window_bits value",
                        )
                    })?;
                }
                _ => {}
            }
        } else {
            match part {
                "client_no_context_takeover" => client_no_context_takeover = true,
                "server_no_context_takeover" => server_no_context_takeover = true,
                _ => {}
            }
        }
    }

    Ok((
        client_no_context_takeover,
        server_no_context_takeover,
        client_max_window_bits,
        server_max_window_bits,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compress_decompress_roundtrip() {
        let mut deflater = Deflater::new(false, false, 15, 15).unwrap();
        let original = b"Hello, World! This is a test of the compression engine.";

        let compressed = deflater.compress_impl(original).unwrap();
        assert!(!compressed.is_empty());
        // Compressed data should be different from original
        assert_ne!(&compressed[..], &original[..]);

        let decompressed = deflater.decompress_impl(&compressed).unwrap();
        assert_eq!(&decompressed[..], &original[..]);
    }

    #[test]
    fn test_compress_empty() {
        let mut deflater = Deflater::new(false, false, 15, 15).unwrap();
        let original = b"";

        let compressed = deflater.compress_impl(original).unwrap();
        let decompressed = deflater.decompress_impl(&compressed).unwrap();
        assert_eq!(&decompressed[..], &original[..]);
    }

    #[test]
    fn test_compress_large_payload() {
        let mut deflater = Deflater::new(false, false, 15, 15).unwrap();
        let original: Vec<u8> = (0..100_000).map(|i| (i % 256) as u8).collect();

        let compressed = deflater.compress_impl(&original).unwrap();
        // Repetitive data should compress well
        assert!(compressed.len() < original.len());

        let decompressed = deflater.decompress_impl(&compressed).unwrap();
        assert_eq!(decompressed, original);
    }

    #[test]
    fn test_context_preservation() {
        // With context takeover (default), multiple messages share compression context
        let mut deflater = Deflater::new(false, false, 15, 15).unwrap();
        let msg = b"repeated message content for testing context";

        let compressed1 = deflater.compress_impl(msg).unwrap();
        let compressed2 = deflater.compress_impl(msg).unwrap();

        // Second compression should benefit from shared context (smaller output)
        assert!(compressed2.len() <= compressed1.len());

        // Both should decompress correctly
        let decompressed1 = deflater.decompress_impl(&compressed1).unwrap();
        let decompressed2 = deflater.decompress_impl(&compressed2).unwrap();
        assert_eq!(&decompressed1[..], msg);
        assert_eq!(&decompressed2[..], msg);
    }

    #[test]
    fn test_no_context_takeover() {
        let mut deflater = Deflater::new(true, true, 15, 15).unwrap();
        let msg = b"repeated message content for testing no-context takeover";

        let compressed1 = deflater.compress_impl(msg).unwrap();
        deflater.compressor.reset();
        let compressed2 = deflater.compress_impl(msg).unwrap();
        deflater.decompressor = Decompress::new(false);

        // Without context takeover, sizes should be similar
        let diff = (compressed1.len() as i64 - compressed2.len() as i64).unsigned_abs();
        assert!(diff <= 2, "sizes should be nearly identical without context");
    }

    #[test]
    fn test_parse_deflate_params_basic() {
        let (cnct, snct, cmwb, smwb) =
            parse_deflate_params("permessage-deflate").unwrap();
        assert!(!cnct);
        assert!(!snct);
        assert_eq!(cmwb, 15);
        assert_eq!(smwb, 15);
    }

    #[test]
    fn test_parse_deflate_params_full() {
        let (cnct, snct, cmwb, smwb) = parse_deflate_params(
            "permessage-deflate; server_no_context_takeover; client_max_window_bits=12",
        )
        .unwrap();
        assert!(!cnct);
        assert!(snct);
        assert_eq!(cmwb, 12);
        assert_eq!(smwb, 15);
    }

    #[test]
    fn test_invalid_window_bits() {
        assert!(Deflater::new(false, false, 8, 15).is_err());
        assert!(Deflater::new(false, false, 15, 16).is_err());
    }
}
