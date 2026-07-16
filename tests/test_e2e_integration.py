"""End-to-end integration tests with the Unity standalone build.

Requires the BCI Unity consumer Linux build and WSL. Marked 'slow'
since it spawns a real Unity process.

NOTE: Because the SHM struct layout changed (heartbeat register added
at offset 0, HEADER_SIZE 16 → 24), the Unity binary must be rebuilt
before these tests will pass.  Run `tools/rebuild_unity.sh linux-mono`.

Scenarios tested:
  - test_e2e_producer_first: producer creates SHM before Unity starts
  - test_e2e_unity_first:     Unity starts before producer (late-binding signal)
"""

import sys, os, subprocess, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.shm_gustation import (
    ShmGustationProducer, ShmGustationConsumer,
    GustationChannel, SIGNAL_NAME,
)

UNITY_PATH = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
LOG_PATH = "/tmp/unity_e2e_test.log"
SHM_NAME = "Local_BCI_GustationRing"
FRAMES = 50


def _has_unity():
    return os.path.isfile(UNITY_PATH)


def _build_compatible():
    """Return True if the Unity binary was built with matching header size.
    
    Checks for the expected total SHM size (8472) in the binary.
    The old layout had SHM_TOTAL_SIZE = 8464.
    """
    if not _has_unity():
        return False
    try:
        import subprocess as _sp
        r = _sp.run(["strings", UNITY_PATH], capture_output=True, text=True, timeout=5)
        return "8472" in r.stdout
    except Exception:
        return False


def _clean():
    subprocess.run(["rm", "-f", LOG_PATH])
    for p in [f"/dev/shm/{SHM_NAME}", f"/dev/shm/sem.{SIGNAL_NAME}"]:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def _wait_for_attach(log, timeout=10):
    for _ in range(int(timeout / 0.2)):
        r = subprocess.run(
            ["grep", "-E", "\\[SHM\\] Attached", log],
            capture_output=True, text=True,
        )
        if r.stdout.strip():
            return r.stdout.strip()
        time.sleep(0.2)
    return None


def _grep_log(pattern):
    r = subprocess.run(
        ["grep", "-E", pattern, LOG_PATH],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


@pytest.mark.slow
def test_e2e_producer_first():
    """Producer creates SHM first; Unity attaches with signal immediately."""
    _clean()

    if not _has_unity():
        pytest.skip("Unity build not found")
    if not _build_compatible():
        pytest.skip("Unity build needs rebuild (SHM layout changed): run tools/rebuild_unity.sh")

    producer = ShmGustationProducer(SHM_NAME, SIGNAL_NAME)
    producer.open()

    proc = subprocess.Popen(
        [UNITY_PATH, "-nographics", "-batchmode", "-logFile", LOG_PATH],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    attach_msg = _wait_for_attach(LOG_PATH)
    assert attach_msg is not None, "Unity never attached"

    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    for pid in range(1, FRAMES + 1):
        producer.write_frame(pid, ch)

    time.sleep(1)
    metrics = producer.get_metrics()
    producer.close()

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()

    assert metrics["frames_written"] > 0, "No frames written"
    assert metrics["buffer_occupancy"] == 0, "Frames stuck in buffer"
    assert metrics["signal_triggers"] > 0, "Signal was never triggered"

    shm_log = _grep_log("\\[SHM\\]")
    assert "sig=True" in shm_log, f"Signal not detected by Unity:\n{shm_log}"


@pytest.mark.slow
def test_e2e_unity_first():
    """Unity starts before producer; signal acquired via late-binding."""
    _clean()

    if not _has_unity():
        pytest.skip("Unity build not found")
    if not _build_compatible():
        pytest.skip("Unity build needs rebuild (SHM layout changed): run tools/rebuild_unity.sh")

    proc = subprocess.Popen(
        [UNITY_PATH, "-nographics", "-batchmode", "-logFile", LOG_PATH],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    # Wait for Unity to start before creating producer
    time.sleep(2)

    producer = ShmGustationProducer(SHM_NAME, SIGNAL_NAME)
    producer.open()

    attach_msg = _wait_for_attach(LOG_PATH)
    assert attach_msg is not None, "Unity never attached after producer created"

    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    for pid in range(1, FRAMES + 1):
        producer.write_frame(pid, ch)

    time.sleep(1)
    metrics = producer.get_metrics()
    producer.close()

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except:
        proc.kill()

    assert metrics["frames_written"] > 0, "No frames written"
    assert metrics["buffer_occupancy"] == 0, "Frames stuck in buffer"

    shm_log = _grep_log("\\[SHM\\]")
    assert "Signal acquired" in shm_log or "sig=True" in shm_log, \
        f"Signal never acquired:\n{shm_log}"
