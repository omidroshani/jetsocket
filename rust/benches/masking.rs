use criterion::{black_box, criterion_group, criterion_main, BenchmarkId, Criterion};

fn bench_apply_mask(c: &mut Criterion) {
    let mut group = c.benchmark_group("apply_mask");
    let mask = [0x37u8, 0xfa, 0x21, 0x3d];

    for size in [64, 256, 1024, 4096, 65536, 1_048_576] {
        let data: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();

        group.bench_with_input(
            BenchmarkId::new("inplace", size),
            &data,
            |b, data| {
                let mut buf = data.clone();
                b.iter(|| {
                    // Re-copy to avoid measuring zeroed data
                    buf.copy_from_slice(data);
                    apply_mask_inplace(black_box(&mut buf), black_box(mask));
                });
            },
        );
    }

    group.finish();
}

/// Inline the masking function to avoid PyO3 dependency in benchmarks.
#[inline]
fn apply_mask_inplace(data: &mut [u8], mask: [u8; 4]) {
    if data.is_empty() {
        return;
    }

    #[cfg(target_arch = "aarch64")]
    unsafe {
        apply_mask_neon(data, mask);
        return;
    }

    #[cfg(target_arch = "x86_64")]
    unsafe {
        apply_mask_sse2(data, mask);
        return;
    }

    #[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
    {
        apply_mask_scalar(data, mask);
    }
}

#[cfg(target_arch = "aarch64")]
#[target_feature(enable = "neon")]
unsafe fn apply_mask_neon(data: &mut [u8], mask: [u8; 4]) {
    use std::arch::aarch64::*;
    let len = data.len();
    let mut i = 0;
    let mask_bytes: [u8; 16] = [
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
    ];
    let mask_vec = vld1q_u8(mask_bytes.as_ptr());
    while i + 16 <= len {
        let chunk = vld1q_u8(data.as_ptr().add(i));
        let result = veorq_u8(chunk, mask_vec);
        vst1q_u8(data.as_mut_ptr().add(i), result);
        i += 16;
    }
    let mask_u32 = u32::from_ne_bytes(mask);
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        data[i..i + 4].copy_from_slice(&(chunk ^ mask_u32).to_ne_bytes());
        i += 4;
    }
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "sse2")]
unsafe fn apply_mask_sse2(data: &mut [u8], mask: [u8; 4]) {
    use std::arch::x86_64::*;
    let len = data.len();
    let mut i = 0;
    let mask_u32 = u32::from_ne_bytes(mask) as i32;
    let mask_vec = _mm_set1_epi32(mask_u32);
    while i + 16 <= len {
        let chunk = _mm_loadu_si128(data.as_ptr().add(i) as *const __m128i);
        let result = _mm_xor_si128(chunk, mask_vec);
        _mm_storeu_si128(data.as_mut_ptr().add(i) as *mut __m128i, result);
        i += 16;
    }
    let mask_u32_unsigned = u32::from_ne_bytes(mask);
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        data[i..i + 4].copy_from_slice(&(chunk ^ mask_u32_unsigned).to_ne_bytes());
        i += 4;
    }
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

#[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
fn apply_mask_scalar(data: &mut [u8], mask: [u8; 4]) {
    let mask_u32 = u32::from_ne_bytes(mask);
    let mask_u64 = (mask_u32 as u64) | ((mask_u32 as u64) << 32);
    let mut i = 0;
    let len = data.len();
    while i + 8 <= len {
        let chunk = u64::from_ne_bytes(data[i..i + 8].try_into().unwrap());
        data[i..i + 8].copy_from_slice(&(chunk ^ mask_u64).to_ne_bytes());
        i += 8;
    }
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        data[i..i + 4].copy_from_slice(&(chunk ^ mask_u32).to_ne_bytes());
        i += 4;
    }
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

criterion_group!(benches, bench_apply_mask);
criterion_main!(benches);
