import subprocess, time, sys, os, signal

unity_path = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import ShmGustationProducer, GustationChannel
from core.shm_gustation import SHM_NAME as PY_SHM, SIGNAL_NAME as PY_SIG

print(f"[TEST] SHM: {PY_SHM}")
print(f"[TEST] Signal: {PY_SIG}")

# Clean stale SHM + semaphore
for target in [f"/dev/shm/{PY_SHM}", f"/dev/shm/sem.{PY_SIG}"]:
    if os.path.exists(target):
        os.remove(target)
        print(f"[TEST] Removed stale: {target}")

# Start Unity
print("[TEST] Starting Unity consumer...")
unity_proc = subprocess.Popen(
    [unity_path, "-nographics", "-batchmode", "-logFile", "/tmp/unity_e2e.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
print(f"[TEST] Unity PID: {unity_proc.pid}")

# Wait for Unity to finish initializing, then create SHM
time.sleep(3)

producer = ShmGustationProducer()
producer.open()

# Wait for Unity to detect and attach to SHM
for _ in range(50):
    result = subprocess.run(
        ["grep", "-q", "Attached", "/tmp/unity_e2e.log"],
        capture_output=True
    )
    if result.returncode == 0:
        connected = subprocess.run(
            ["grep", "Attached", "/tmp/unity_e2e.log"],
            capture_output=True, text=True
        )
        print(f"[TEST] Unity connected: {connected.stdout.strip()}")
        break
    time.sleep(0.2)
else:
    print("[TEST] WARNING: Unity did not connect within timeout, writing anyway")

print("[TEST] Writing 50 gustation frames...")
for pid in range(50):
    channels = [
        GustationChannel(channel_id=pid % 4, intensity=0.1 * (pid % 10),
                         duration_ms=50.0, chemical_profile=pid & 0xFF),
    ]
    ok = producer.write_frame(packet_id=pid, channels=channels)
    if not ok:
        print(f"  Frame {pid}: DROPPED (buffer full)")

time.sleep(1.0)

metrics = producer.get_metrics()
print(f"[TEST] Producer: {metrics}")
producer.close()

unity_proc.terminate()
try:
    unity_proc.wait(timeout=5)
except:
    unity_proc.kill()
    print("[TEST] Force killed Unity")

# Check Unity log for connection
log_check = subprocess.run(
    ["grep", "-E", "\\[SHM\\]", "/tmp/unity_e2e.log"],
    capture_output=True, text=True
)
print(f"[TEST] Unity SHM log: {log_check.stdout.strip()}")

if metrics["buffer_occupancy"] == 0 and metrics["frames_written"] > 0:
    print("[TEST] SUCCESS: All frames consumed!")
elif metrics["buffer_occupancy"] > 0:
    print(f"[TEST] FAIL: {metrics['buffer_occupancy']} frames stuck in buffer")
else:
    print("[TEST] FAIL: No frames written")

print("[TEST] Done")
