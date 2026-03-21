#![no_main]

use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;

#[derive(Arbitrary, Debug)]
struct FrameInput {
    opcode: u8,
    payload: Vec<u8>,
    mask: bool,
    fin: bool,
}

/// Encode then decode a frame, verify roundtrip integrity.
fuzz_target!(|input: FrameInput| {
    // Only use valid opcodes
    let opcode = match input.opcode % 6 {
        0 => 0x0, // Continuation
        1 => 0x1, // Text
        2 => 0x2, // Binary
        3 => 0x8, // Close
        4 => 0x9, // Ping
        _ => 0xA, // Pong
    };

    // Control frames must be <= 125 bytes and FIN
    let (payload, fin) = if opcode >= 0x8 {
        let truncated = if input.payload.len() > 125 {
            &input.payload[..125]
        } else {
            &input.payload
        };
        (truncated, true)
    } else {
        (input.payload.as_slice(), input.fin)
    };

    // Limit payload size in fuzzer to avoid OOM
    if payload.len() > 65536 {
        return;
    }

    let encoded = encode_frame(opcode, payload, input.mask, fin);
    let parsed = parse_frame(&encoded);

    if let Some((parsed_opcode, parsed_payload, _)) = parsed {
        assert_eq!(parsed_opcode & 0x0F, opcode);
        assert_eq!(parsed_payload, payload);
    }
});

fn encode_frame(opcode: u8, payload: &[u8], mask: bool, fin: bool) -> Vec<u8> {
    let payload_len = payload.len();
    let mask_size = if mask { 4 } else { 0 };
    let len_bytes = if payload_len <= 125 {
        1
    } else if payload_len <= 65535 {
        3
    } else {
        9
    };
    let header_size = 1 + len_bytes + mask_size;
    let mut frame = Vec::with_capacity(header_size + payload_len);

    let first_byte = if fin { 0x80 } else { 0x00 } | opcode;
    frame.push(first_byte);

    let mask_bit = if mask { 0x80u8 } else { 0x00 };
    if payload_len <= 125 {
        frame.push(mask_bit | (payload_len as u8));
    } else if payload_len <= 65535 {
        frame.push(mask_bit | 126);
        frame.extend_from_slice(&(payload_len as u16).to_be_bytes());
    } else {
        frame.push(mask_bit | 127);
        frame.extend_from_slice(&(payload_len as u64).to_be_bytes());
    }

    if mask {
        let mask_key = [0x12u8, 0x34, 0x56, 0x78]; // Fixed for determinism
        frame.extend_from_slice(&mask_key);
        let mut masked = payload.to_vec();
        for (i, byte) in masked.iter_mut().enumerate() {
            *byte ^= mask_key[i % 4];
        }
        frame.extend_from_slice(&masked);
    } else {
        frame.extend_from_slice(payload);
    }

    frame
}

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
            if data.len() < 4 { return None; }
            (4 + mask_size, u16::from_be_bytes([data[2], data[3]]) as usize)
        }
        127 => {
            if data.len() < 10 { return None; }
            (10 + mask_size, u64::from_be_bytes(data[2..10].try_into().unwrap()) as usize)
        }
        _ => return None,
    };

    let total_size = header_size + payload_len;
    if data.len() < total_size { return None; }

    let mut payload = data[header_size..total_size].to_vec();
    if masked {
        let ms = header_size - mask_size;
        let mask = [data[ms], data[ms+1], data[ms+2], data[ms+3]];
        for (i, b) in payload.iter_mut().enumerate() {
            *b ^= mask[i % 4];
        }
    }

    Some((opcode, payload, total_size))
}
