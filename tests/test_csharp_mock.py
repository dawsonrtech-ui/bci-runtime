"""CI integration: verifies the C# mock consumer compiles and communicates
with the Python SHM producer across processes.

Marked as 'slow' since it requires dotnet SDK and native bridge DLL.
"""

import sys, os, subprocess, threading, time, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.shm_gustation import (
    ShmGustationProducer,
    GustationChannel,
)

SHM_NAME = "Local_BCI_CITestRing"
SIGNAL_NAME = "Local_BCI_CITestWake"
CI_TAG = "--" + SHM_NAME  # unique marker for leftover SHM cleanup
CSHARP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "csharp_mock",
)
FRAMES = 50


def _has_dotnet():
    try:
        p = subprocess.run(
            ["dotnet", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return p.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _has_bridge():
    from core.native_bridge import _find_lib
    return _find_lib() is not None


@pytest.mark.slow
def test_csharp_mock_build():
    """Verify the C# project compiles."""
    result = subprocess.run(
        ["dotnet", "build", CSHARP_DIR, "--nologo"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"dotnet build failed:\n{result.stderr}"
    print(f"[CI] C# build OK")


@pytest.mark.slow
def test_csharp_mock_cross_process():
    """End-to-end: Python producer streams frames, C# mock receives them."""
    import mmap
    try:
        mmap.mmap(-1, 8464, tagname=SHM_NAME, access=mmap.ACCESS_WRITE).close()
    except Exception:
        pass

    proc = subprocess.Popen(
        ["dotnet", "run", "--project", CSHARP_DIR, "--", SHM_NAME, SIGNAL_NAME],
        cwd=CSHARP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    ready = False
    for line in iter(proc.stdout.readline, ""):
        if "Listening" in line:
            ready = True
            break
        if "FAIL" in line or "error" in line.lower():
            proc.kill()
            pytest.fail(f"C# mock failed at startup: {line}")

    assert ready, "C# mock never signalled readiness"

    # Run producer
    prod = ShmGustationProducer(SHM_NAME, SIGNAL_NAME)
    prod.open()
    ch = [GustationChannel(0, 0.5, 100.0, 1, (0, 0, 0))]
    for pid in range(1, FRAMES + 1):
        prod.write_frame(pid, ch)
        time.sleep(0.005)
    prod.close()

    # Drain C# output
    time.sleep(0.5)
    output = []
    for line in iter(proc.stdout.readline, ""):
        output.append(line)
    proc.wait(timeout=5)

    output_text = "".join(output)

    errors = "FAIL" in output_text or "error" in output_text
    frame_lines = [l for l in output if "[FRAME #" in l]
    seq_faults = [l for l in output if "SEQ FAULT" in l]

    assert not errors, f"C# mock reported errors:\n{output_text}"
    assert len(frame_lines) > 0, f"No frames received by C# mock:\n{output_text}"
    assert len(seq_faults) == 0, f"Sequence faults detected:\n{''.join(seq_faults)}"

    print(f"[CI] C# cross-process: {len(frame_lines)} frames, 0 seq faults")
