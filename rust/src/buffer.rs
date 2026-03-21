//! High-performance circular buffer for message buffering.
//!
//! This module provides a ring buffer implementation optimized for WebSocket
//! message buffering with configurable overflow policies.

use pyo3::prelude::*;

/// Policy for handling buffer overflow.
#[pyclass(eq, eq_int)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OverflowPolicy {
    /// Drop the oldest message when full (FIFO eviction).
    DropOldest = 0,
    /// Drop the incoming message when full.
    DropNewest = 1,
    /// Raise an error when full.
    Error = 2,
}

impl OverflowPolicy {
    /// Parse policy from a string.
    pub fn from_str(s: &str) -> PyResult<Self> {
        match s {
            "drop_oldest" => Ok(OverflowPolicy::DropOldest),
            "drop_newest" => Ok(OverflowPolicy::DropNewest),
            "error" => Ok(OverflowPolicy::Error),
            _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid overflow policy: {}. Expected 'drop_oldest', 'drop_newest', or 'error'",
                s
            ))),
        }
    }
}

/// Wrapper for buffered items that holds both PyObject and optional sequence ID.
struct BufferItem {
    object: PyObject,
    sequence_id: Option<PyObject>,
}

/// High-performance circular buffer for message storage.
///
/// This buffer provides O(1) push and pop operations with configurable
/// overflow behavior. It is optimized for WebSocket message buffering
/// scenarios where messages need to be replayed after reconnection.
///
/// Example:
///     >>> buffer = RingBuffer(100, "drop_oldest")
///     >>> buffer.push(message)
///     >>> buffer.push(message2)
///     >>> messages = buffer.drain()
#[pyclass]
pub struct RingBuffer {
    buffer: Vec<Option<BufferItem>>,
    head: usize,
    tail: usize,
    len: usize,
    capacity: usize,
    policy: OverflowPolicy,
    total_dropped: usize,
}

#[pymethods]
impl RingBuffer {
    /// Create a new ring buffer with the given capacity and overflow policy.
    ///
    /// Args:
    ///     capacity: Maximum number of items the buffer can hold.
    ///     policy: Overflow policy ('drop_oldest', 'drop_newest', or 'error').
    ///
    /// Raises:
    ///     ValueError: If capacity is 0 or policy is invalid.
    #[new]
    #[pyo3(signature = (capacity, policy = "drop_oldest"))]
    pub fn new(capacity: usize, policy: &str) -> PyResult<Self> {
        if capacity == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Buffer capacity must be greater than 0",
            ));
        }

        let policy = OverflowPolicy::from_str(policy)?;

        // Initialize with None values
        let mut buffer = Vec::with_capacity(capacity);
        buffer.resize_with(capacity, || None);

        Ok(Self {
            buffer,
            head: 0,
            tail: 0,
            len: 0,
            capacity,
            policy,
            total_dropped: 0,
        })
    }

    /// Push an item onto the buffer.
    ///
    /// Args:
    ///     item: The item to push.
    ///     sequence_id: Optional sequence identifier for the item.
    ///
    /// Returns:
    ///     True if the item was added, False if it was dropped (drop_newest policy).
    ///
    /// Raises:
    ///     BufferOverflowError: If buffer is full and policy is 'error'.
    #[pyo3(signature = (item, sequence_id = None))]
    pub fn push(&mut self, py: Python<'_>, item: PyObject, sequence_id: Option<PyObject>) -> PyResult<bool> {
        if self.len == self.capacity {
            match self.policy {
                OverflowPolicy::DropOldest => {
                    // Drop the oldest (head) and advance
                    self.head = (self.head + 1) % self.capacity;
                    self.len -= 1;
                    self.total_dropped += 1;
                }
                OverflowPolicy::DropNewest => {
                    // Don't add the new item
                    self.total_dropped += 1;
                    return Ok(false);
                }
                OverflowPolicy::Error => {
                    // Import and raise BufferOverflowError with keyword arguments
                    let kwargs = pyo3::types::PyDict::new_bound(py);
                    kwargs.set_item("capacity", self.capacity)?;
                    kwargs.set_item("current_size", self.len)?;
                    let exc_class = py.import_bound("wsfabric.exceptions")?.getattr("BufferOverflowError")?;
                    return Err(PyErr::from_value_bound(exc_class.call(
                        ("Buffer is full",),
                        Some(&kwargs),
                    )?));
                }
            }
        }

        // Add the new item at tail
        self.buffer[self.tail] = Some(BufferItem {
            object: item,
            sequence_id,
        });
        self.tail = (self.tail + 1) % self.capacity;
        self.len += 1;

        Ok(true)
    }

    /// Pop the oldest item from the buffer.
    ///
    /// Returns:
    ///     The oldest item, or None if the buffer is empty.
    pub fn pop(&mut self) -> Option<PyObject> {
        if self.len == 0 {
            return None;
        }

        let item = self.buffer[self.head].take();
        self.head = (self.head + 1) % self.capacity;
        self.len -= 1;

        item.map(|bi| bi.object)
    }

    /// Peek at the oldest item without removing it.
    ///
    /// Returns:
    ///     The oldest item, or None if the buffer is empty.
    pub fn peek(&self, py: Python<'_>) -> Option<PyObject> {
        if self.len == 0 {
            return None;
        }

        self.buffer[self.head].as_ref().map(|bi| bi.object.clone_ref(py))
    }

    /// Drain all items from the buffer.
    ///
    /// Returns:
    ///     A list of all items in order (oldest first).
    pub fn drain(&mut self) -> Vec<PyObject> {
        let mut items = Vec::with_capacity(self.len);

        while self.len > 0 {
            if let Some(item) = self.pop() {
                items.push(item);
            }
        }

        items
    }

    /// Drain all items with their sequence IDs.
    ///
    /// Returns:
    ///     A list of (item, sequence_id) tuples in order (oldest first).
    pub fn drain_with_sequences(&mut self) -> Vec<(PyObject, Option<PyObject>)> {
        let mut items = Vec::with_capacity(self.len);

        while self.len > 0 {
            if let Some(bi) = self.buffer[self.head].take() {
                items.push((bi.object, bi.sequence_id));
            }
            self.head = (self.head + 1) % self.capacity;
            self.len -= 1;
        }

        items
    }

    /// Get the number of items in the buffer.
    #[getter]
    pub fn len(&self) -> usize {
        self.len
    }

    /// Check if the buffer is empty.
    #[getter]
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Get the buffer capacity.
    #[getter]
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Check if the buffer is full.
    #[getter]
    pub fn is_full(&self) -> bool {
        self.len == self.capacity
    }

    /// Get the fill ratio (0.0 to 1.0).
    #[getter]
    pub fn fill_ratio(&self) -> f64 {
        self.len as f64 / self.capacity as f64
    }

    /// Get the total number of dropped messages.
    #[getter]
    pub fn total_dropped(&self) -> usize {
        self.total_dropped
    }

    /// Get the overflow policy.
    #[getter]
    pub fn policy(&self) -> OverflowPolicy {
        self.policy
    }

    /// Clear all items from the buffer.
    pub fn clear(&mut self) {
        for slot in &mut self.buffer {
            *slot = None;
        }
        self.head = 0;
        self.tail = 0;
        self.len = 0;
    }

    /// Reset dropped counter.
    pub fn reset_dropped_counter(&mut self) {
        self.total_dropped = 0;
    }

    fn __repr__(&self) -> String {
        format!(
            "RingBuffer(capacity={}, len={}, fill_ratio={:.2}, policy={:?})",
            self.capacity, self.len, self.fill_ratio(), self.policy
        )
    }

    fn __len__(&self) -> usize {
        self.len
    }

    fn __bool__(&self) -> bool {
        self.len > 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_buffer() {
        Python::with_gil(|_py| {
            let buffer = RingBuffer::new(10, "drop_oldest").unwrap();
            assert_eq!(buffer.capacity(), 10);
            assert_eq!(buffer.len(), 0);
            assert!(buffer.is_empty());
            assert!(!buffer.is_full());
            assert_eq!(buffer.fill_ratio(), 0.0);
        });
    }

    #[test]
    fn test_invalid_capacity() {
        Python::with_gil(|_py| {
            let result = RingBuffer::new(0, "drop_oldest");
            assert!(result.is_err());
        });
    }

    #[test]
    fn test_invalid_policy() {
        Python::with_gil(|_py| {
            let result = RingBuffer::new(10, "invalid");
            assert!(result.is_err());
        });
    }

    #[test]
    fn test_push_pop() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(3, "drop_oldest").unwrap();

            assert!(buffer.push(py, "item1".into_py(py), None).unwrap());
            assert!(buffer.push(py, "item2".into_py(py), None).unwrap());
            assert!(buffer.push(py, "item3".into_py(py), None).unwrap());

            assert_eq!(buffer.len(), 3);
            assert!(buffer.is_full());

            // Pop should return in FIFO order
            let popped1 = buffer.pop().unwrap();
            assert_eq!(popped1.extract::<&str>(py).unwrap(), "item1");

            let popped2 = buffer.pop().unwrap();
            assert_eq!(popped2.extract::<&str>(py).unwrap(), "item2");

            let popped3 = buffer.pop().unwrap();
            assert_eq!(popped3.extract::<&str>(py).unwrap(), "item3");

            assert!(buffer.pop().is_none());
            assert!(buffer.is_empty());
        });
    }

    #[test]
    fn test_drop_oldest_policy() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(2, "drop_oldest").unwrap();

            buffer.push(py, "item1".into_py(py), None).unwrap();
            buffer.push(py, "item2".into_py(py), None).unwrap();
            buffer.push(py, "item3".into_py(py), None).unwrap(); // Should drop item1

            assert_eq!(buffer.len(), 2);
            assert_eq!(buffer.total_dropped(), 1);

            // Should return item2, item3 (item1 was dropped)
            let items = buffer.drain();
            assert_eq!(items.len(), 2);
            assert_eq!(items[0].extract::<&str>(py).unwrap(), "item2");
            assert_eq!(items[1].extract::<&str>(py).unwrap(), "item3");
        });
    }

    #[test]
    fn test_drop_newest_policy() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(2, "drop_newest").unwrap();

            buffer.push(py, "item1".into_py(py), None).unwrap();
            buffer.push(py, "item2".into_py(py), None).unwrap();
            let added = buffer.push(py, "item3".into_py(py), None).unwrap(); // Should not add

            assert!(!added); // Should return false indicating item was not added
            assert_eq!(buffer.len(), 2);
            assert_eq!(buffer.total_dropped(), 1);

            // Should return item1, item2 (item3 was dropped)
            let items = buffer.drain();
            assert_eq!(items.len(), 2);
            assert_eq!(items[0].extract::<&str>(py).unwrap(), "item1");
            assert_eq!(items[1].extract::<&str>(py).unwrap(), "item2");
        });
    }

    #[test]
    fn test_drain() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(5, "drop_oldest").unwrap();

            for i in 0..5 {
                buffer.push(py, i.into_py(py), None).unwrap();
            }

            let items = buffer.drain();
            assert_eq!(items.len(), 5);
            assert!(buffer.is_empty());

            for (idx, item) in items.iter().enumerate() {
                assert_eq!(item.extract::<usize>(py).unwrap(), idx);
            }
        });
    }

    #[test]
    fn test_clear() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(5, "drop_oldest").unwrap();

            for i in 0..5 {
                buffer.push(py, i.into_py(py), None).unwrap();
            }

            assert_eq!(buffer.len(), 5);
            buffer.clear();
            assert_eq!(buffer.len(), 0);
            assert!(buffer.is_empty());
        });
    }

    #[test]
    fn test_peek() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(3, "drop_oldest").unwrap();

            assert!(buffer.peek(py).is_none());

            buffer.push(py, "first".into_py(py), None).unwrap();
            buffer.push(py, "second".into_py(py), None).unwrap();

            let peeked = buffer.peek(py).unwrap();
            assert_eq!(peeked.extract::<&str>(py).unwrap(), "first");

            // Peek should not remove the item
            assert_eq!(buffer.len(), 2);
        });
    }

    #[test]
    fn test_wrap_around() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(3, "drop_oldest").unwrap();

            // Fill buffer
            buffer.push(py, "a".into_py(py), None).unwrap();
            buffer.push(py, "b".into_py(py), None).unwrap();
            buffer.push(py, "c".into_py(py), None).unwrap();

            // Pop one
            buffer.pop();

            // Push another (should wrap around)
            buffer.push(py, "d".into_py(py), None).unwrap();

            let items = buffer.drain();
            assert_eq!(items.len(), 3);
            assert_eq!(items[0].extract::<&str>(py).unwrap(), "b");
            assert_eq!(items[1].extract::<&str>(py).unwrap(), "c");
            assert_eq!(items[2].extract::<&str>(py).unwrap(), "d");
        });
    }

    #[test]
    fn test_sequence_ids() {
        Python::with_gil(|py| {
            let mut buffer = RingBuffer::new(3, "drop_oldest").unwrap();

            buffer.push(py, "msg1".into_py(py), Some(1i32.into_py(py))).unwrap();
            buffer.push(py, "msg2".into_py(py), Some(2i32.into_py(py))).unwrap();
            buffer.push(py, "msg3".into_py(py), None).unwrap();

            let items = buffer.drain_with_sequences();
            assert_eq!(items.len(), 3);

            assert_eq!(items[0].0.extract::<&str>(py).unwrap(), "msg1");
            assert_eq!(items[0].1.as_ref().unwrap().extract::<i32>(py).unwrap(), 1);

            assert_eq!(items[1].0.extract::<&str>(py).unwrap(), "msg2");
            assert_eq!(items[1].1.as_ref().unwrap().extract::<i32>(py).unwrap(), 2);

            assert_eq!(items[2].0.extract::<&str>(py).unwrap(), "msg3");
            assert!(items[2].1.is_none());
        });
    }
}
