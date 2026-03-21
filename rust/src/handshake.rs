//! WebSocket handshake implementation (RFC 6455 Section 4).
//!
//! This module handles the HTTP/1.1 upgrade handshake for WebSocket connections,
//! including Sec-WebSocket-Key generation and Sec-WebSocket-Accept validation.

use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sha1::{Digest, Sha1};

use crate::errors::HandshakeError;

/// The WebSocket GUID used for accept key calculation (RFC 6455 Section 4.2.2).
const WS_GUID: &str = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

/// Generate a random Sec-WebSocket-Key for the handshake.
///
/// Returns a base64-encoded 16-byte random value.
#[pyfunction]
pub fn generate_key() -> String {
    let random_bytes: [u8; 16] = rand::random();
    BASE64.encode(random_bytes)
}

/// Validate the Sec-WebSocket-Accept header value.
///
/// Args:
///     key: The Sec-WebSocket-Key that was sent in the request
///     accept: The Sec-WebSocket-Accept received in the response
///
/// Returns:
///     True if the accept value is valid
#[pyfunction]
pub fn validate_accept(key: &str, accept: &str) -> bool {
    let expected = compute_accept(key);
    expected == accept
}

/// Compute the expected Sec-WebSocket-Accept value for a given key.
fn compute_accept(key: &str) -> String {
    let mut hasher = Sha1::new();
    hasher.update(key.as_bytes());
    hasher.update(WS_GUID.as_bytes());
    let result = hasher.finalize();
    BASE64.encode(result)
}

/// WebSocket handshake helper.
///
/// Provides utilities for building and parsing HTTP/1.1 upgrade requests/responses.
#[pyclass]
pub struct Handshake {
    key: String,
    host: String,
    path: String,
    origin: Option<String>,
    subprotocols: Vec<String>,
    extensions: Vec<String>,
    extra_headers: Vec<(String, String)>,
}

#[pymethods]
impl Handshake {
    /// Create a new handshake builder.
    ///
    /// Args:
    ///     host: The Host header value
    ///     path: The request path (e.g., "/ws")
    ///     origin: Optional Origin header
    ///     subprotocols: Optional list of subprotocols to request
    ///     extensions: Optional list of extensions to request
    ///     extra_headers: Optional additional headers as (name, value) tuples
    #[new]
    #[pyo3(signature = (host, path, origin=None, subprotocols=None, extensions=None, extra_headers=None))]
    pub fn new(
        host: String,
        path: String,
        origin: Option<String>,
        subprotocols: Option<Vec<String>>,
        extensions: Option<Vec<String>>,
        extra_headers: Option<Vec<(String, String)>>,
    ) -> Self {
        Self {
            key: generate_key(),
            host,
            path,
            origin,
            subprotocols: subprotocols.unwrap_or_default(),
            extensions: extensions.unwrap_or_default(),
            extra_headers: extra_headers.unwrap_or_default(),
        }
    }

    /// Get the generated Sec-WebSocket-Key.
    #[getter]
    fn key(&self) -> &str {
        &self.key
    }

    /// Build the HTTP/1.1 upgrade request.
    ///
    /// Returns the complete HTTP request as bytes.
    fn build_request<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.build_request_bytes())
    }

    /// Parse the HTTP response and validate the handshake.
    ///
    /// Args:
    ///     response: The raw HTTP response bytes
    ///
    /// Returns:
    ///     A dict with:
    ///         - status: HTTP status code
    ///         - headers: Dict of response headers
    ///         - subprotocol: Selected subprotocol (if any)
    ///         - extensions: List of accepted extensions
    ///
    /// Raises:
    ///     ValueError: If the handshake is invalid
    fn parse_response(&self, response: &[u8]) -> PyResult<HandshakeResult> {
        let response_str = std::str::from_utf8(response)
            .map_err(|_| HandshakeError::InvalidResponse)?;

        // Split headers from body
        let header_end = response_str
            .find("\r\n\r\n")
            .ok_or(HandshakeError::InvalidResponse)?;
        let header_section = &response_str[..header_end];

        // Parse status line
        let mut lines = header_section.lines();
        let status_line = lines.next().ok_or(HandshakeError::InvalidResponse)?;

        // Parse "HTTP/1.1 101 Switching Protocols"
        let mut parts = status_line.split_whitespace();
        let _version = parts.next().ok_or(HandshakeError::InvalidResponse)?;
        let status: u16 = parts
            .next()
            .ok_or(HandshakeError::InvalidResponse)?
            .parse()
            .map_err(|_| HandshakeError::InvalidResponse)?;

        if status != 101 {
            let reason = parts.collect::<Vec<_>>().join(" ");
            return Err(HandshakeError::HttpError { status, reason }.into());
        }

        // Parse headers
        let mut headers: std::collections::HashMap<String, String> = std::collections::HashMap::new();
        for line in lines {
            if let Some((name, value)) = line.split_once(':') {
                headers.insert(
                    name.trim().to_lowercase(),
                    value.trim().to_string(),
                );
            }
        }

        // Validate required headers
        let upgrade = headers
            .get("upgrade")
            .ok_or_else(|| HandshakeError::MissingHeader("Upgrade".to_string()))?;
        if !upgrade.eq_ignore_ascii_case("websocket") {
            return Err(HandshakeError::InvalidResponse.into());
        }

        let connection = headers
            .get("connection")
            .ok_or_else(|| HandshakeError::MissingHeader("Connection".to_string()))?;
        if !connection.to_lowercase().contains("upgrade") {
            return Err(HandshakeError::InvalidResponse.into());
        }

        // Validate Sec-WebSocket-Accept
        let accept = headers
            .get("sec-websocket-accept")
            .ok_or_else(|| HandshakeError::MissingHeader("Sec-WebSocket-Accept".to_string()))?;
        if !validate_accept(&self.key, accept) {
            return Err(HandshakeError::InvalidAccept.into());
        }

        // Extract optional fields
        let subprotocol = headers.get("sec-websocket-protocol").cloned();
        let extensions = headers
            .get("sec-websocket-extensions")
            .map(|e| e.split(';').map(|s| s.trim().to_string()).collect())
            .unwrap_or_default();

        Ok(HandshakeResult {
            status,
            headers,
            subprotocol,
            extensions,
        })
    }
}

impl Handshake {
    /// Internal method to build request as Vec<u8> (for testing and internal use).
    fn build_request_bytes(&self) -> Vec<u8> {
        let mut request = format!(
            "GET {} HTTP/1.1\r\n\
             Host: {}\r\n\
             Upgrade: websocket\r\n\
             Connection: Upgrade\r\n\
             Sec-WebSocket-Key: {}\r\n\
             Sec-WebSocket-Version: 13\r\n",
            self.path, self.host, self.key
        );

        if let Some(ref origin) = self.origin {
            request.push_str(&format!("Origin: {}\r\n", origin));
        }

        if !self.subprotocols.is_empty() {
            request.push_str(&format!(
                "Sec-WebSocket-Protocol: {}\r\n",
                self.subprotocols.join(", ")
            ));
        }

        if !self.extensions.is_empty() {
            request.push_str(&format!(
                "Sec-WebSocket-Extensions: {}\r\n",
                self.extensions.join("; ")
            ));
        }

        for (name, value) in &self.extra_headers {
            request.push_str(&format!("{}: {}\r\n", name, value));
        }

        request.push_str("\r\n");
        request.into_bytes()
    }
}

/// Result of a successful WebSocket handshake.
#[pyclass]
#[derive(Clone)]
pub struct HandshakeResult {
    #[pyo3(get)]
    pub status: u16,
    #[pyo3(get)]
    pub headers: std::collections::HashMap<String, String>,
    #[pyo3(get)]
    pub subprotocol: Option<String>,
    #[pyo3(get)]
    pub extensions: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_key_length() {
        let key = generate_key();
        // Base64 of 16 bytes = 24 characters (with padding)
        assert_eq!(key.len(), 24);
    }

    #[test]
    fn test_validate_accept() {
        // Example from RFC 6455 Section 4.2.2
        let key = "dGhlIHNhbXBsZSBub25jZQ==";
        let expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=";
        assert!(validate_accept(key, expected_accept));
    }

    #[test]
    fn test_validate_accept_invalid() {
        let key = "dGhlIHNhbXBsZSBub25jZQ==";
        assert!(!validate_accept(key, "invalid"));
    }

    #[test]
    fn test_build_request() {
        let handshake = Handshake::new(
            "example.com".to_string(),
            "/ws".to_string(),
            None,
            None,
            None,
            None,
        );

        let request = handshake.build_request_bytes();
        let request_str = String::from_utf8(request).unwrap();

        assert!(request_str.contains("GET /ws HTTP/1.1\r\n"));
        assert!(request_str.contains("Host: example.com\r\n"));
        assert!(request_str.contains("Upgrade: websocket\r\n"));
        assert!(request_str.contains("Connection: Upgrade\r\n"));
        assert!(request_str.contains("Sec-WebSocket-Key:"));
        assert!(request_str.contains("Sec-WebSocket-Version: 13\r\n"));
        assert!(request_str.ends_with("\r\n\r\n"));
    }

    #[test]
    fn test_parse_response_success() {
        let handshake = Handshake {
            key: "dGhlIHNhbXBsZSBub25jZQ==".to_string(),
            host: "example.com".to_string(),
            path: "/ws".to_string(),
            origin: None,
            subprotocols: vec![],
            extensions: vec![],
            extra_headers: vec![],
        };

        let response = b"HTTP/1.1 101 Switching Protocols\r\n\
            Upgrade: websocket\r\n\
            Connection: Upgrade\r\n\
            Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\
            \r\n";

        let result = handshake.parse_response(response).unwrap();
        assert_eq!(result.status, 101);
    }

    #[test]
    fn test_parse_response_invalid_accept() {
        let handshake = Handshake {
            key: "dGhlIHNhbXBsZSBub25jZQ==".to_string(),
            host: "example.com".to_string(),
            path: "/ws".to_string(),
            origin: None,
            subprotocols: vec![],
            extensions: vec![],
            extra_headers: vec![],
        };

        let response = b"HTTP/1.1 101 Switching Protocols\r\n\
            Upgrade: websocket\r\n\
            Connection: Upgrade\r\n\
            Sec-WebSocket-Accept: invalid\r\n\
            \r\n";

        assert!(handshake.parse_response(response).is_err());
    }
}
