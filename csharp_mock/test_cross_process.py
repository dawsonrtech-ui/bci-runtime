"""Cross-process: Python producer -> C# mock consumer over SHM ring buffer.
"""

import sys, os, time, subprocess, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.shm_gustation import (
    ShmGustationProducer,
    GustationChannel, SHM_NAME, SIGNAL_NAME,
)

FRAME_COUNT = 150


def run_producer():
    prod = ShmGustationProducer(SHM_NAME, SIGNAL_NAME)
    prod.open()
    try:
        ch = [
            GustationChannel(0, 1.0, 50.0, 3, (0, 0, 0)),
            GustationChannel(1, 0.75, 100.0, 7, (0, 0, 0)),
            GustationChannel(2, 0.5, 150.0, 1, (0, 0, 0)),
            GustationChannel(3, 0.25, 200.0, 5, (0, 0, 0)),
            GustationChannel(4, 0.0, 0.0, 0, (0, 0, 0)),
        ]
        written = 0
        for pid in range(1, FRAME_COUNT + 1):
            for i in range(5):
                ch[i].intensity = (pid % 100) / 100.0 * (5 - i) / 5.0
            ok = prod.write_frame(pid, ch)
            if ok:
                written += 1
            time.sleep(0.033)
        print(f"[PRODUCER] Wrote {written}/{FRAME_COUNT} frames.", flush=True)
    finally:
        prod.close()


if __name__ == "__main__":
    csharp_dir = os.path.dirname(os.path.abspath(__file__))

    proc = subprocess.Popen(
        ["dotnet", "run", "--project", csharp_dir],
        cwd=csharp_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    start = time.monotonic()
    ready = False
    output_lines = []

    for line in iter(proc.stdout.readline, ""):
        output_lines.append(line)
        print(f"[C#] {line}", end="")

        if "Listening" in line:
            ready = True
            print(f"[CROSS-PROC] C# ready (build {time.monotonic() - start:.1f}s)", flush=True)
            break

    if not ready:
        print("[CROSS-PROC] FAIL: C# not ready", flush=True)
        proc.kill()
        sys.exit(1)

    prod_thread = threading.Thread(target=run_producer, daemon=True)
    prod_thread.start()

    for line in iter(proc.stdout.readline, ""):
        output_lines.append(line)
        print(f"[C#] {line}", end="")

    proc.wait(timeout=10)
    print(f"[CROSS-PROC] C# exited ({proc.returncode})", flush=True)
    prod_thread.join(timeout=5)

    output_text = "".join(output_lines)
    passed = True

    frame_count = output_text.count("[FRAME #")
    if frame_count == 0:
        print("[CROSS-PROC TEST] FAIL: no frames received")
        passed = False
    else:
        print(f"[CROSS-PROC TEST] Frames received: {frame_count}")

    seq_faults = output_text.count("SEQ FAULT")
    if seq_faults:
        print(f"[CROSS-PROC TEST] {seq_faults} sequence faults!")
        passed = False

    if "[FAIL]" in output_text:
        print("[CROSS-PROC TEST] FAIL: errors found")
        passed = False

    if passed:
        print("[CROSS-PROC TEST] ALL CHECKS PASSED")
    else:
        sys.exit(1)
