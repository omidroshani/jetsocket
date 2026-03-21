#![no_main]

use flate2::{Compress, Compression, Decompress, FlushCompress, FlushDecompress};
use libfuzzer_sys::fuzz_target;

const DEFLATE_TRAILER: [u8; 4] = [0x00, 0x00, 0xFF, 0xFF];

/// Compress then decompress arbitrary data, verify roundtrip.
fuzz_target!(|data: &[u8]| {
    // Limit input size to avoid OOM in fuzzer
    if data.len() > 1024 * 1024 {
        return;
    }

    if let Ok(compressed) = compress(data) {
        if let Ok(decompressed) = decompress(&compressed) {
            assert_eq!(data, &decompressed[..], "Roundtrip mismatch");
        }
    }
});

fn compress(data: &[u8]) -> Result<Vec<u8>, String> {
    let mut compressor = Compress::new(Compression::default(), false);
    let max_output = data.len() + (data.len() / 100) + 256;
    let mut output = vec![0u8; max_output];

    let before_out = compressor.total_out();
    compressor
        .compress(data, &mut output, FlushCompress::Sync)
        .map_err(|e| format!("{}", e))?;
    let produced = (compressor.total_out() - before_out) as usize;
    output.truncate(produced);

    // Strip sync trailer
    if output.len() >= 4 && output[output.len() - 4..] == DEFLATE_TRAILER {
        output.truncate(output.len() - 4);
    }

    Ok(output)
}

fn decompress(data: &[u8]) -> Result<Vec<u8>, String> {
    let mut decompressor = Decompress::new(false);
    let mut input = Vec::with_capacity(data.len() + 4);
    input.extend_from_slice(data);
    input.extend_from_slice(&DEFLATE_TRAILER);

    let mut output = Vec::with_capacity(data.len() * 4);
    let mut buf = [0u8; 8192];
    let mut input_pos = 0;

    loop {
        let before_in = decompressor.total_in();
        let before_out = decompressor.total_out();

        let status = decompressor
            .decompress(&input[input_pos..], &mut buf, FlushDecompress::Sync)
            .map_err(|e| format!("{}", e))?;

        let consumed = (decompressor.total_in() - before_in) as usize;
        let produced = (decompressor.total_out() - before_out) as usize;
        input_pos += consumed;
        output.extend_from_slice(&buf[..produced]);

        // Limit decompressed output to prevent decompression bombs
        if output.len() > 16 * 1024 * 1024 {
            return Err("decompressed output too large".into());
        }

        if status == flate2::Status::StreamEnd || (consumed == 0 && produced == 0) {
            break;
        }
    }

    Ok(output)
}
