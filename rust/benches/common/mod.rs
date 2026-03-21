/// Encode a WebSocket frame (standalone, no PyO3 dependency).
pub fn encode_frame(opcode: u8, payload: &[u8], mask: bool, fin: bool, rsv1: bool) -> Vec<u8> {
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

    let mut first_byte = if fin { 0x80 } else { 0x00 } | opcode;
    if rsv1 {
        first_byte |= 0x40;
    }
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
        let mask_key = [0x37u8, 0xfa, 0x21, 0x3d];
        frame.extend_from_slice(&mask_key);
        let mut masked_payload = payload.to_vec();
        for (i, byte) in masked_payload.iter_mut().enumerate() {
            *byte ^= mask_key[i % 4];
        }
        frame.extend_from_slice(&masked_payload);
    } else {
        frame.extend_from_slice(payload);
    }

    frame
}

/// Parse frames from raw bytes (standalone, no PyO3 dependency).
pub fn parse_frame(data: &[u8]) -> Option<(u8, Vec<u8>, usize)> {
    if data.len() < 2 {
        return None;
    }

    let first_byte = data[0];
    let opcode = first_byte & 0x0F;
    let second_byte = data[1];
    let masked = second_byte & 0x80 != 0;
    let initial_len = second_byte & 0x7F;

    let (header_size, payload_len) = match initial_len {
        0..=125 => (2 + if masked { 4 } else { 0 }, initial_len as usize),
        126 => {
            if data.len() < 4 {
                return None;
            }
            let len = u16::from_be_bytes([data[2], data[3]]) as usize;
            (4 + if masked { 4 } else { 0 }, len)
        }
        127 => {
            if data.len() < 10 {
                return None;
            }
            let len = u64::from_be_bytes(data[2..10].try_into().unwrap()) as usize;
            (10 + if masked { 4 } else { 0 }, len)
        }
        _ => return None,
    };

    let total_size = header_size + payload_len;
    if data.len() < total_size {
        return None;
    }

    let payload = data[header_size..total_size].to_vec();
    Some((opcode, payload, total_size))
}
