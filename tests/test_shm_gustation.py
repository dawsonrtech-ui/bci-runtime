import sys, os, time
import ctypes
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_struct_sizes():
    from core.shm_gustation import (
        GustationChannel, ShmSlot, SharedRingBuffer,
        SHM_TOTAL_SIZE, RING_BUFFER_SIZE,
    )

    assert ctypes.sizeof(GustationChannel) == 16, \
        f"GustationChannel size: {ctypes.sizeof(GustationChannel)}"
    assert ctypes.sizeof(ShmSlot) == 264, \
        f"ShmSlot size: {ctypes.sizeof(ShmSlot)}"
    assert ctypes.sizeof(SharedRingBuffer) == 24 + 32 * 264, \
        f"SharedRingBuffer size: {ctypes.sizeof(SharedRingBuffer)}"
    assert ctypes.sizeof(SharedRingBuffer) == SHM_TOTAL_SIZE
    assert RING_BUFFER_SIZE == 32
    print(f"Struct sizes OK: GustationChannel={ctypes.sizeof(GustationChannel)}B, "
          f"ShmSlot={ctypes.sizeof(ShmSlot)}B, "
          f"RingBuffer={ctypes.sizeof(SharedRingBuffer)}B")


def test_gustation_channel_fields():
    from core.shm_gustation import GustationChannel

    ch = GustationChannel()
    ch.channel_id = 7
    ch.intensity = 0.85
    ch.duration_ms = 120.0
    ch.chemical_profile = 3

    assert ch.channel_id == 7
    assert abs(ch.intensity - 0.85) < 1e-6
    assert abs(ch.duration_ms - 120.0) < 1e-6
    assert ch.chemical_profile == 3
    print(f"GustationChannel fields OK: {ch}")


def test_producer_consumer_roundtrip():
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer,
        GustationChannel,
    )

    producer = ShmGustationProducer("Local_BCI_TestRing")
    consumer = ShmGustationConsumer("Local_BCI_TestRing")

    try:
        producer.open()
        consumer.open()

        channels = [
            GustationChannel(1, 0.85, 100.0, 2, (0, 0, 0)),
            GustationChannel(2, 0.12, 50.0, 0, (0, 0, 0)),
        ]

        ok = producer.write_frame(42, channels)
        assert ok, "write_frame returned False"

        frames = consumer.read_all()
        assert len(frames) == 1, f"expected 1 frame, got {len(frames)}"
        assert frames[0].packet_id == 42, \
            f"packet_id: {frames[0].packet_id}"
        assert frames[0].channel_count == 2

        c0 = frames[0].channels[0]
        assert c0.channel_id == 1
        assert abs(c0.intensity - 0.85) < 1e-6
        assert c0.chemical_profile == 2

        c1 = frames[0].channels[1]
        assert c1.channel_id == 2
        assert abs(c1.intensity - 0.12) < 1e-6

        print("Producer/consumer roundtrip OK")

    finally:
        producer.close()
        consumer.close()


def test_multi_frame_ring():
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer,
        GustationChannel,
    )

    producer = ShmGustationProducer("Local_BCI_TestMulti")
    consumer = ShmGustationConsumer("Local_BCI_TestMulti")

    try:
        producer.open()
        consumer.open()

        for i in range(10):
            ch = [GustationChannel(i, 0.1 * i, 50.0, i % 5, (0, 0, 0))]
            producer.write_frame(i, ch)

        frames = consumer.read_all()
        assert len(frames) == 10, f"expected 10, got {len(frames)}"
        for i, slot in enumerate(frames):
            assert slot.packet_id == i, f"packet_id at {i}: {slot.packet_id}"
        print(f"Multi-frame ring OK: {len(frames)} frames")
    finally:
        producer.close()
        consumer.close()


def test_ring_full_drop():
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer,
        GustationChannel, RING_BUFFER_SIZE,
    )

    producer = ShmGustationProducer("Local_BCI_TestFull")
    consumer = ShmGustationConsumer("Local_BCI_TestFull")

    try:
        producer.open()
        consumer.open()

        ch = [GustationChannel(0, 1.0, 100.0, 0, (0, 0, 0))]

        for i in range(RING_BUFFER_SIZE):
            ok = producer.write_frame(i, ch)
            assert ok, f"write_frame({i}) failed when ring not full"

        ok = producer.write_frame(999, ch)
        assert not ok, "write_frame should fail on full ring"

        frames = consumer.read_all()
        assert len(frames) == RING_BUFFER_SIZE

        ok = producer.write_frame(1000, ch)
        assert ok, "write_frame should succeed after consumer drain"
        print(f"Ring full/drop OK: produced {RING_BUFFER_SIZE}, "
              f"drained {len(frames)}, re-filled 1")

    finally:
        producer.close()
        consumer.close()


def test_producer_consumer_different_objects():
    if os.name != "nt":
        pytest.skip("Named mmap (tagname) is Windows-only")
    from core.shm_gustation import GustationChannel, ShmSlot
    from core.shm_gustation import SharedRingBuffer, SHM_TOTAL_SIZE
    import mmap

    import ctypes
    name = "Local_BCI_TestIsolation"
    mm = mmap.mmap(-1, SHM_TOTAL_SIZE, tagname=name, access=mmap.ACCESS_WRITE)
    raw = (ctypes.c_uint8 * SHM_TOTAL_SIZE).from_buffer(mm)
    ptr = ctypes.cast(raw, ctypes.POINTER(SharedRingBuffer))
    ring = ptr.contents

    ch = GustationChannel(5, 0.75, 200.0, 1, (0, 0, 0))
    slot = ring.slots[0]
    slot.packet_id = 77
    slot.channel_count = 1
    slot.channels[0] = ch
    ring.head = 1

    mm_read = mmap.mmap(-1, SHM_TOTAL_SIZE, tagname=name, access=mmap.ACCESS_WRITE)
    raw_read = (ctypes.c_uint8 * SHM_TOTAL_SIZE).from_buffer(mm_read)
    ptr_read = ctypes.cast(raw_read, ctypes.POINTER(SharedRingBuffer))
    ring_read = ptr_read.contents
    assert ring_read.head == 1

    slot_read = ring_read.slots[0]
    assert slot_read.packet_id == 77
    assert slot_read.channels[0].channel_id == 5
    assert abs(slot_read.channels[0].intensity - 0.75) < 1e-6

    import gc as _gc
    del raw, ptr, ring, slot, raw_read, ptr_read, ring_read, slot_read
    _gc.collect()
    mm.close()
    mm_read.close()
    print("Cross-mmap isolation OK")


def test_producer_heartbeat():
    """Verify producer increments heartbeat on every write."""
    from core.shm_gustation import ShmGustationProducer, GustationChannel
    producer = ShmGustationProducer("Local_BCI_HBTest", "Local_BCI_HBTestSig")
    try:
        producer.open()
        assert producer._ring.producer_heartbeat == 0, "initial heartbeat should be 0"
        ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
        producer.write_frame(1, ch)
        assert producer._ring.producer_heartbeat == 1, "heartbeat should be 1 after first write"
        producer.write_frame(2, ch)
        producer.write_frame(3, ch)
        assert producer._ring.producer_heartbeat == 3, "heartbeat should be 3 after 3 writes"
        print(f"Producer heartbeat OK ({producer._ring.producer_heartbeat})")
    finally:
        producer.close()


def test_consumer_heartbeat_detects_stall():
    """Consumer can read heartbeat and detect when producer stops."""
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer, GustationChannel,
    )
    producer = ShmGustationProducer("Local_BCI_HBTest2", "Local_BCI_HBTestSig2")
    consumer = ShmGustationConsumer("Local_BCI_HBTest2", "Local_BCI_HBTestSig2")
    try:
        producer.open()
        consumer.open()
        assert consumer.get_heartbeat() == 0, "initial heartbeat mismatch"
        ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
        for i in range(5):
            producer.write_frame(i, ch)
        consumer.read_all()
        assert consumer.get_heartbeat() == 5, f"heartbeat mismatch: {consumer.get_heartbeat()}"
        assert consumer.producer_alive() is True
        # After producer close, consumer heartbeat still returns last value
        producer.close()
        hb = consumer.get_heartbeat()
        assert hb == 5, f"last heartbeat should persist: {hb}"
        print(f"Consumer heartbeat OK ({hb})")
    finally:
        try: producer.close()
        except: pass
        consumer.close()


if __name__ == "__main__":
    test_struct_sizes()
    test_gustation_channel_fields()
    test_producer_consumer_roundtrip()
    test_multi_frame_ring()
    test_ring_full_drop()
    test_producer_consumer_different_objects()
    test_producer_heartbeat()
    test_consumer_heartbeat_detects_stall()
    print("\nAll shared-memory gustation tests PASSED")
