import sys, os, time, ctypes
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


HAS_NATIVE = False
lib = None

def _load_signal_lib():
    from core.native_bridge import _find_lib
    path = _find_lib()
    assert path, "bridge DLL not found"
    lib = ctypes.CDLL(path)
    lib.create_os_signal.argtypes = [ctypes.c_char_p]
    lib.create_os_signal.restype = ctypes.c_void_p
    lib.open_os_signal.argtypes = [ctypes.c_char_p]
    lib.open_os_signal.restype = ctypes.c_void_p
    lib.trigger_os_signal.argtypes = [ctypes.c_void_p]
    lib.trigger_os_signal.restype = None
    lib.wait_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wait_os_signal.restype = ctypes.c_int
    lib.close_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.close_os_signal.restype = None
    return lib

try:
    lib = _load_signal_lib()
    HAS_NATIVE = True
except (OSError, AssertionError):
    pass

needs_native = pytest.mark.skipif(
    not HAS_NATIVE,
    reason="native bridge DLL not available on this platform",
)


SIG_NAME = "Local_BCI_TestSignal"


@needs_native
def test_create_and_destroy():
    lib = _load_signal_lib()
    h = lib.create_os_signal(SIG_NAME.encode("utf-8"))
    assert h is not None and h != 0, f"create failed, handle={h}"
    print(f"Created signal: {h:#x}")
    lib.close_os_signal(h, SIG_NAME.encode("utf-8"))
    print("create_and_destroy OK")


@needs_native
def test_open_and_trigger():
    lib = _load_signal_lib()
    h = lib.create_os_signal(SIG_NAME.encode("utf-8"))
    assert h != 0

    h2 = lib.open_os_signal(SIG_NAME.encode("utf-8"))
    assert h2 != 0, "open_os_signal failed"
    print(f"Opened second handle: {h2:#x}")

    lib.trigger_os_signal(h)
    rc = lib.wait_os_signal(h2, 100)
    assert rc == 0, f"wait_os_signal returned {rc}"

    lib.close_os_signal(h, SIG_NAME.encode("utf-8"))
    lib.close_os_signal(h2, None)
    print("open_and_trigger OK")


@needs_native
def test_timeout():
    lib = _load_signal_lib()
    h = lib.create_os_signal(SIG_NAME.encode("utf-8"))
    assert h != 0

    rc = lib.wait_os_signal(h, 50)
    assert rc == -1, f"expected timeout, got {rc}"

    lib.close_os_signal(h, SIG_NAME.encode("utf-8"))
    print("timeout OK")


@needs_native
def test_empty_to_non_empty_trigger():
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer,
        GustationChannel, SIGNAL_NAME,
    )
    from core.native_bridge import _find_lib
    import mmap

    lib = _load_signal_lib()

    producer = ShmGustationProducer("Local_BCI_TestWake", SIGNAL_NAME)
    consumer = ShmGustationConsumer("Local_BCI_TestWake")

    try:
        producer.open()

        sig = lib.open_os_signal(SIGNAL_NAME.encode("utf-8"))
        assert sig != 0, "failed to open signal from test"

        ch = [GustationChannel(0, 0.5, 100.0, 0, (0, 0, 0))]

        ok = producer.write_frame(1, ch)
        assert ok

        rc = lib.wait_os_signal(sig, 500)
        assert rc == 0, f"signal not triggered, wait returned {rc}"

        ok = producer.write_frame(2, ch)
        assert ok

        rc = lib.wait_os_signal(sig, 200)
        assert rc == -1, "signal should not have been triggered (buffer was not empty)"

        print("Empty -> non-empty trigger OK")

    finally:
        producer.close()
        lib.close_os_signal(sig, None)
        consumer.close()


def test_producer_consumer_with_signal():
    from core.shm_gustation import (
        ShmGustationProducer, ShmGustationConsumer,
        GustationChannel,
    )

    producer = ShmGustationProducer("Local_BCI_TestSigFlow", "Local_BCI_TestSigFlowWake")
    consumer = ShmGustationConsumer("Local_BCI_TestSigFlow")

    try:
        producer.open()
        consumer.open()

        ch = [GustationChannel(1, 0.9, 200.0, 2, (0, 0, 0))]
        ok = producer.write_frame(42, ch)
        assert ok

        import time as _t
        _t.sleep(0.05)

        frames = consumer.read_all()
        assert len(frames) == 1, f"expected 1 frame, got {len(frames)}"
        assert frames[0].packet_id == 42
        assert frames[0].channels[0].chemical_profile == 2

        print(f"Producer/consumer with signal OK (packet {frames[0].packet_id})")

    finally:
        producer.close()
        consumer.close()


if __name__ == "__main__":
    test_create_and_destroy()
    test_open_and_trigger()
    test_timeout()
    test_empty_to_non_empty_trigger()
    test_producer_consumer_with_signal()
    print("\nAll shared-memory signal tests PASSED")
