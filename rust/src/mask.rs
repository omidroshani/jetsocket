//! WebSocket frame masking utilities.
//!
//! Client-to-server frames must be masked per RFC 6455 Section 5.3.
//! This module provides SIMD-accelerated masking on supported platforms
//! with fallback to word-at-a-time operations.

use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Apply WebSocket masking to data and return new bytes.
///
/// The masking algorithm is:
///   j = i MOD 4
///   transformed[i] = original[i] XOR mask[j]
#[pyfunction]
pub fn apply_mask(py: Python<'_>, data: &[u8], mask: [u8; 4]) -> Py<PyBytes> {
    let mut output = data.to_vec();
    apply_mask_inplace(&mut output, mask);
    PyBytes::new_bound(py, &output).into()
}

/// Apply mask in place without allocation.
///
/// Dispatches to the best available implementation:
/// - NEON (aarch64): 16 bytes at a time
/// - SSE2 (x86_64): 16 bytes at a time
/// - Scalar: 8 bytes at a time (u64)
#[inline]
pub fn apply_mask_inplace(data: &mut [u8], mask: [u8; 4]) {
    if data.is_empty() {
        return;
    }

    #[cfg(target_arch = "aarch64")]
    {
        // NEON is always available on aarch64
        // Safety: NEON is guaranteed on aarch64
        unsafe { apply_mask_neon(data, mask) };
        return;
    }

    #[cfg(target_arch = "x86_64")]
    {
        // SSE2 is always available on x86_64
        // Safety: SSE2 is guaranteed on x86_64
        unsafe { apply_mask_sse2(data, mask) };
        return;
    }

    #[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
    {
        apply_mask_scalar(data, mask);
    }
}

/// NEON-accelerated masking (aarch64). Processes 16 bytes at a time.
#[cfg(target_arch = "aarch64")]
#[target_feature(enable = "neon")]
unsafe fn apply_mask_neon(data: &mut [u8], mask: [u8; 4]) {
    use std::arch::aarch64::*;

    let len = data.len();
    let mut i = 0;

    // Build a 16-byte mask by repeating the 4-byte mask 4 times
    let mask_bytes: [u8; 16] = [
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
        mask[0], mask[1], mask[2], mask[3],
    ];
    let mask_vec = vld1q_u8(mask_bytes.as_ptr());

    // Process 16 bytes at a time with NEON
    while i + 16 <= len {
        let chunk = vld1q_u8(data.as_ptr().add(i));
        let result = veorq_u8(chunk, mask_vec);
        vst1q_u8(data.as_mut_ptr().add(i), result);
        i += 16;
    }

    // Handle remaining bytes with scalar fallback
    let mask_u32 = u32::from_ne_bytes(mask);
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        let masked = chunk ^ mask_u32;
        data[i..i + 4].copy_from_slice(&masked.to_ne_bytes());
        i += 4;
    }
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

/// SSE2-accelerated masking (x86_64). Processes 16 bytes at a time.
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "sse2")]
unsafe fn apply_mask_sse2(data: &mut [u8], mask: [u8; 4]) {
    use std::arch::x86_64::*;

    let len = data.len();
    let mut i = 0;

    // Build 128-bit mask by repeating the 4-byte mask
    let mask_u32 = u32::from_ne_bytes(mask) as i32;
    let mask_vec = _mm_set1_epi32(mask_u32);

    // Process 16 bytes at a time with SSE2
    while i + 16 <= len {
        let chunk = _mm_loadu_si128(data.as_ptr().add(i) as *const __m128i);
        let result = _mm_xor_si128(chunk, mask_vec);
        _mm_storeu_si128(data.as_mut_ptr().add(i) as *mut __m128i, result);
        i += 16;
    }

    // Handle remaining bytes with scalar fallback
    let mask_u32_unsigned = u32::from_ne_bytes(mask);
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        let masked = chunk ^ mask_u32_unsigned;
        data[i..i + 4].copy_from_slice(&masked.to_ne_bytes());
        i += 4;
    }
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

/// Scalar fallback masking using word-at-a-time operations.
#[cfg(not(any(target_arch = "aarch64", target_arch = "x86_64")))]
fn apply_mask_scalar(data: &mut [u8], mask: [u8; 4]) {
    let mask_u32 = u32::from_ne_bytes(mask);
    let mask_u64 = (mask_u32 as u64) | ((mask_u32 as u64) << 32);

    let mut i = 0;
    let len = data.len();

    // Process 8 bytes at a time
    while i + 8 <= len {
        let chunk = u64::from_ne_bytes(data[i..i + 8].try_into().unwrap());
        let masked = chunk ^ mask_u64;
        data[i..i + 8].copy_from_slice(&masked.to_ne_bytes());
        i += 8;
    }

    // Process 4 bytes at a time
    while i + 4 <= len {
        let chunk = u32::from_ne_bytes(data[i..i + 4].try_into().unwrap());
        let masked = chunk ^ mask_u32;
        data[i..i + 4].copy_from_slice(&masked.to_ne_bytes());
        i += 4;
    }

    // Remaining bytes
    while i < len {
        data[i] ^= mask[i % 4];
        i += 1;
    }
}

/// Generate a random 4-byte masking key.
#[inline]
pub fn generate_mask() -> [u8; 4] {
    rand::random()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mask_roundtrip() {
        let original = b"Hello, World!";
        let mask = [0x37, 0xfa, 0x21, 0x3d];

        let mut data = original.to_vec();
        apply_mask_inplace(&mut data, mask);

        // Data should be different after masking
        assert_ne!(&data, original);

        // Applying mask again should restore original
        apply_mask_inplace(&mut data, mask);
        assert_eq!(&data, original);
    }

    #[test]
    fn test_mask_empty() {
        let mut data: Vec<u8> = vec![];
        let mask = [0x12, 0x34, 0x56, 0x78];
        apply_mask_inplace(&mut data, mask);
        assert!(data.is_empty());
    }

    #[test]
    fn test_mask_various_lengths() {
        let mask = [0xaa, 0xbb, 0xcc, 0xdd];

        for len in 1..=64 {
            let original: Vec<u8> = (0..len).map(|i| i as u8).collect();
            let mut data = original.clone();
            apply_mask_inplace(&mut data, mask);
            apply_mask_inplace(&mut data, mask);
            assert_eq!(data, original, "Failed for length {}", len);
        }
    }

    #[test]
    fn test_mask_large_payload() {
        let mask = [0x12, 0x34, 0x56, 0x78];
        let original: Vec<u8> = (0..10_000).map(|i| (i % 256) as u8).collect();
        let mut data = original.clone();
        apply_mask_inplace(&mut data, mask);
        assert_ne!(data, original);
        apply_mask_inplace(&mut data, mask);
        assert_eq!(data, original);
    }
}
