import subprocess, time, sys, os, signal

unity_path = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import ShmGustationProducer, GustationChannel
from core.shm_gustation import SHM_NAME as PY_SHM

# Clean stale SHM
for p in ["/dev/shm/" + PY_SHM]:
    if os.path.exists(p):
        os.remove(p)

# Start Unity and capture stdout in real-time
print("[TEST] Starting Unity consumer...")
unity_proc = subprocess.Popen(
    [unity_path, "-nographics", "-batchmode", "-logFile", "/tmp/unity_e2e.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
print(f"[TEST] Unity PID: {unity_proc.pid}")
time.sleep(1)

# Check if Unity connected yet
import subprocess as sp
result = sp.run(["grep", "-E", "\\[SHM\\]", "/tmp/unity_e2e.log"], capture_output=True, text=True)
print(f"[TEST] Unity SHM status: {result.stdout.strip()}")

# Create producer and write frames
print("[TEST] Creating producer...")
producer = ShmGustationProducer()
producer.open()

# Write frames slowly
for pid in range(10):
    channels = [GustationChannel(channel_id=pid % 4, intensity=0.5,
                                 duration_ms=50.0, chemical_profile=pid & 0xFF)]
    ok = producer.write_frame(packet_id=pid, channels=channels)
    status = "OK" if ok else "DROP"
    print(f"  Frame {pid}: {status}")
    time.sleep(0.5)  # Half second between frames

time.sleep(1)
metrics = producer.get_metrics()
print(f"[TEST] Producer: {metrics}")
producer.close()

# Check Unity log
result = sp.run(["grep", "-E", "\\[SHM\\]", "/tmp/unity_e2e.log"], capture_output=True, text=True)
print(f"[TEST] Unity final SHM status: {result.stdout.strip()}")

unity_proc.terminate()
try:
    unity_proc.wait(timeout=3)
except:
    unity_proc.kill()

if metrics["frames_written"] > 0 and metrics["buffer_occupancy"] == 0:
    print("[TEST] SUCCESS: All frames consumed by Unity!")
elif metrics["buffer_occupancy"] > 0:
    print(f"[TEST] FAIL: {metrics['buffer_occupancy']} frames stuck in buffer")
else:
    print("[TEST] FAIL: No frames produced")
print("[TEST] Done")
