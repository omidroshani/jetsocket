#![no_main]

use libfuzzer_sys::fuzz_target;

/// Feed arbitrary bytes as HTTP handshake response.
/// Must never panic — only return errors gracefully.
fuzz_target!(|data: &[u8]| {
    let _ = parse_handshake_response(data);
});

/// Standalone handshake response parser (no PyO3 dependency).
fn parse_handshake_response(data: &[u8]) -> Result<(u16, Vec<(String, String)>), &'static str> {
    let response = std::str::from_utf8(data).map_err(|_| "invalid utf8")?;

    // Find header end
    let header_end = response.find("\r\n\r\n").ok_or("no header end")?;
    let header_section = &response[..header_end];
    let mut lines = header_section.split("\r\n");

    // Parse status line
    let status_line = lines.next().ok_or("empty response")?;
    let parts: Vec<&str> = status_line.splitn(3, ' ').collect();
    if parts.len() < 2 {
        return Err("invalid status line");
    }

    let status: u16 = parts[1].parse().map_err(|_| "invalid status code")?;

    // Parse headers
    let mut headers = Vec::new();
    for line in lines {
        if let Some(colon) = line.find(':') {
            let name = line[..colon].trim().to_lowercase();
            let value = line[colon + 1..].trim().to_string();
            headers.push((name, value));
        }
    }

    Ok((status, headers))
}
