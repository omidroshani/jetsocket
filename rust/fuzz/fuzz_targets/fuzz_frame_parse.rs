#![no_main]

use libfuzzer_sys::fuzz_target;

/// Parse arbitrary bytes as WebSocket frames.
/// Must never panic or cause undefined behavior.
fuzz_target!(|data: &[u8]| {
    let _ = parse_frame(data);
});

/// Standalone frame parser (no PyO3 dependency).
fn parse_frame(data: &[u8]) -> Option<(u8, Vec<u8>, usize)> {
    if data.len() < 2 {
        return None;
    }

    let first_byte = data[0];
    let opcode = first_byte & 0x0F;
    let second_byte = data[1];
    let masked = second_byte & 0x80 != 0;
    let initial_len = second_byte & 0x7F;

    let mask_size = if masked { 4 } else { 0 };
    let (header_size, payload_len) = match initial_len {
        0..=125 => (2 + mask_size, initial_len as usize),
        126 => {
            if data.len() < 4 {
                return None;
            }
            let len = u16::from_be_bytes([data[2], data[3]]) as usize;
            (4 + mask_size, len)
        }
        127 => {
            if data.len() < 10 {
                return None;
            }
            let len = u64::from_be_bytes(data[2..10].try_into().unwrap()) as usize;
            // Limit to 16MB to avoid OOM in fuzzer
            if len > 16 * 1024 * 1024 {
                return None;
            }
            (10 + mask_size, len)
        }
        _ => return None,
    };

    let total_size = header_size + payload_len;
    if data.len() < total_size {
        return None;
    }

    let mut payload = data[header_size..total_size].to_vec();

    // Apply mask if present
    if masked && header_size >= mask_size {
        let mask_start = header_size - mask_size;
        let mask = [
            data[mask_start],
            data[mask_start + 1],
            data[mask_start + 2],
            data[mask_start + 3],
        ];
        for (i, byte) in payload.iter_mut().enumerate() {
            *byte ^= mask[i % 4];
        }
    }

    Some((opcode, payload, total_size))
}
