use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};
use flate2::{Compress, Compression, Decompress, FlushCompress, FlushDecompress};

const DEFLATE_TRAILER: [u8; 4] = [0x00, 0x00, 0xFF, 0xFF];

fn compress_data(compressor: &mut Compress, data: &[u8]) -> Vec<u8> {
    let mut output = Vec::with_capacity(data.len());
    let mut buf = [0u8; 8192];
    let mut input_pos = 0;

    loop {
        let before_in = compressor.total_in();
        let before_out = compressor.total_out();
        let flush = if input_pos >= data.len() {
            FlushCompress::Sync
        } else {
            FlushCompress::None
        };
        let _ = compressor.compress(&data[input_pos..], &mut buf, flush).unwrap();
        let consumed = (compressor.total_in() - before_in) as usize;
        let produced = (compressor.total_out() - before_out) as usize;
        input_pos += consumed;
        output.extend_from_slice(&buf[..produced]);
        if flush == FlushCompress::Sync && produced == 0 && input_pos >= data.len() {
            break;
        }
        if consumed == 0 && produced == 0 {
            break;
        }
    }
    // Final sync flush
    loop {
        let before_out = compressor.total_out();
        let _ = compressor.compress(&[], &mut buf, FlushCompress::Sync).unwrap();
        let produced = (compressor.total_out() - before_out) as usize;
        output.extend_from_slice(&buf[..produced]);
        if produced == 0 { break; }
    }
    if output.len() >= 4 && output[output.len() - 4..] == DEFLATE_TRAILER {
        output.truncate(output.len() - 4);
    }
    output
}

fn decompress_data(decompressor: &mut Decompress, data: &[u8]) -> Vec<u8> {
    let mut input = Vec::with_capacity(data.len() + 4);
    input.extend_from_slice(data);
    input.extend_from_slice(&DEFLATE_TRAILER);

    let mut output = Vec::with_capacity(data.len() * 2);
    let mut buf = [0u8; 8192];
    let mut input_pos = 0;

    loop {
        let before_in = decompressor.total_in();
        let before_out = decompressor.total_out();
        let status = decompressor
            .decompress(&input[input_pos..], &mut buf, FlushDecompress::Sync)
            .unwrap();
        let consumed = (decompressor.total_in() - before_in) as usize;
        let produced = (decompressor.total_out() - before_out) as usize;
        input_pos += consumed;
        output.extend_from_slice(&buf[..produced]);
        if status == flate2::Status::StreamEnd || (consumed == 0 && produced == 0) {
            break;
        }
    }
    output
}

fn bench_compress(c: &mut Criterion) {
    let mut group = c.benchmark_group("compress");

    for size in [128, 1024, 65536] {
        // JSON-like data compresses well
        let data: Vec<u8> = format!(
            r#"{{"symbol":"BTCUSDT","price":"50000.00","quantity":"0.001","timestamp":{},"data":"{}"}}"#,
            1234567890,
            "x".repeat(size.max(100) - 100)
        ).into_bytes();

        group.bench_with_input(
            BenchmarkId::new("json", data.len()),
            &data,
            |b, data| {
                let mut compressor = Compress::new(Compression::default(), false);
                b.iter(|| {
                    compressor.reset();
                    compress_data(black_box(&mut compressor), black_box(data))
                });
            },
        );
    }

    group.finish();
}

fn bench_decompress(c: &mut Criterion) {
    let mut group = c.benchmark_group("decompress");

    for size in [128, 1024, 65536] {
        let data: Vec<u8> = vec![b'a'; size];
        let mut compressor = Compress::new(Compression::default(), false);
        let compressed = compress_data(&mut compressor, &data);

        group.bench_with_input(
            BenchmarkId::new("text", size),
            &compressed,
            |b, compressed| {
                let mut decompressor = Decompress::new(false);
                b.iter(|| {
                    decompressor = Decompress::new(false);
                    decompress_data(black_box(&mut decompressor), black_box(compressed))
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_compress, bench_decompress);
criterion_main!(benches);
