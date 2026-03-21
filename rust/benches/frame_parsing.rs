use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

mod common;

fn bench_frame_encode(c: &mut Criterion) {
    let mut group = c.benchmark_group("frame_encode");

    for size in [0, 125, 1024, 65536, 1_048_576] {
        let payload: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();

        group.bench_with_input(
            BenchmarkId::new("masked", size),
            &payload,
            |b, payload| {
                b.iter(|| {
                    common::encode_frame(black_box(0x01), black_box(payload), true, true, false);
                });
            },
        );
    }

    group.finish();
}

fn bench_frame_parse(c: &mut Criterion) {
    let mut group = c.benchmark_group("frame_parse");

    for size in [125, 1024, 65536] {
        // Build a valid unmasked text frame
        let payload: Vec<u8> = vec![b'a'; size];
        let frame_bytes = common::encode_frame(0x01, &payload, false, true, false);

        group.bench_with_input(
            BenchmarkId::new("unmasked", size),
            &frame_bytes,
            |b, frame_bytes| {
                b.iter(|| {
                    common::parse_frame(black_box(frame_bytes));
                });
            },
        );
    }

    group.finish();
}

criterion_group!(benches, bench_frame_encode, bench_frame_parse);
criterion_main!(benches);
