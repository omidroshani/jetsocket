# Security Audit — WSFabric

**Date:** 2026-03-21
**Scope:** TLS configuration, frame handling, input validation, DoS protection

## Findings

### 1. TLS Configuration — PASS

- `create_default_ssl_context()` uses `ssl.create_default_context()` which enforces TLS 1.2+ and loads system CA certificates
- `check_hostname = True` and `verify_mode = ssl.CERT_REQUIRED` are set explicitly in `AsyncTransport.connect()`
- SSLv3, TLSv1.0, TLSv1.1 are disabled by Python's defaults
- Users can pass custom `ssl_context` for advanced use cases

### 2. Frame Masking — PASS

- `FrameParser.encode()` defaults to `mask=True` (client-to-server masking per RFC 6455)
- Mask keys are generated via `os.urandom()` (cryptographic randomness)
- Mask keys are verified to be unique across frames (not deterministic)

### 3. Input Validation — PASS

- `max_frame_size` (default 16MB) prevents memory exhaustion from oversized frames
- `max_message_size` (default 64MB) limits assembled message size
- Control frames limited to 125 bytes per RFC 6455
- Fragmented control frames are rejected
- Reserved bits RSV2/RSV3 cause protocol errors (RSV1 allowed for compression)
- Invalid opcodes (3-7, B-F) are rejected

### 4. Close Handshake — PASS

- Close frames are echoed per RFC 6455
- `_handle_close_frame` uses `contextlib.suppress(Exception)` for echo (best-effort, documented)
- Close codes 1000-4999 are handled
- Empty close frames (no payload) are valid

### 5. Decompression Bomb — ADVISORY

**Risk:** Medium
**Status:** Documented, mitigation recommended

The `Deflater.decompress()` has no maximum decompressed size limit. A malicious server could send a small compressed payload that expands to gigabytes, causing OOM.

**Current mitigation:** The `max_message_size` limit on `FrameParser` limits the compressed payload size, but the decompressed output could be much larger.

**Recommendation:** Add a `max_decompressed_size` parameter to `Deflater` (default: 64MB matching `max_message_size`).

### 6. Parser Buffer Accumulation — LOW RISK

**Status:** Documented

`FrameParser.feed()` appends to an internal buffer. If a client continuously feeds incomplete frame headers, the buffer grows. The `max_frame_size` check occurs after length parsing, not on buffer size.

**Mitigation:** The buffer only grows when the caller feeds data. In normal operation, the transport reads fixed-size chunks (64KB). An attacker would need to send data that looks like valid frame headers but never completes. The transport's read timeout provides implicit protection.

### 7. Handshake Accept Validation — LOW RISK

**Status:** Documented

`validate_accept()` uses standard string equality (`==`) which is not constant-time. Since the Sec-WebSocket-Accept value is derived from a publicly visible key (sent in the request), timing attacks are not a realistic threat. For defense-in-depth, `hmac.compare_digest()` could be used.

## Summary

| Category | Status | Risk |
|----------|--------|------|
| TLS Configuration | PASS | None |
| Frame Masking | PASS | None |
| Input Validation | PASS | None |
| Close Handshake | PASS | None |
| Decompression Bomb | ADVISORY | Medium |
| Buffer Accumulation | DOCUMENTED | Low |
| Accept Timing | DOCUMENTED | Low |
