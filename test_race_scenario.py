"""Test E2E with Unity starting before producer (simulates real deployment race)."""
import subprocess, time, sys, os

unity_path = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import ShmGustationProducer, GustationChannel, SIGNAL_NAME

# Start fresh
subprocess.run(["rm", "-f", "/tmp/race_test.log"])
for target in [f"/dev/shm/Local_BCI_GustationRing", f"/dev/shm/sem.Local_BCI_GustationWake"]:
    try:
        os.remove(target)
    except FileNotFoundError:
        pass

# Start Unity first
proc = subprocess.Popen(
    [unity_path, "-nographics", "-batchmode", "-logFile", "/tmp/race_test.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)

# Wait a bit, then create producer (simulates real timing)
time.sleep(2)

producer = ShmGustationProducer()
producer.open()

# Wait for Unity to attach
for _ in range(100):
    r = subprocess.run(["grep", "-E", "\\[SHM\\] Attached", "/tmp/race_test.log"],
                       capture_output=True, text=True)
    if r.stdout.strip():
        print(f"Unity: {r.stdout.strip()}")
        break
    time.sleep(0.2)
else:
    print("Unity never attached")

# Write some frames
ch = [GustationChannel(0, 0.5, 50, 1, (0,0,0))]
for pid in range(20):
    producer.write_frame(pid, ch)
time.sleep(0.5)

metrics = producer.get_metrics()
print(f"Producer: {metrics}")
producer.close()

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

# Parse Unity log for signal state (check for late-binding acquisition)
r = subprocess.run(["grep", "-E", "\\[SHM\\]", "/tmp/race_test.log"],
                   capture_output=True, text=True)
print(f"Unity SHM: {r.stdout.strip()}")

success = metrics["buffer_occupancy"] == 0 and metrics["frames_written"] > 0
sig_ok = "sig=True" in r.stdout or "Signal acquired" in r.stdout
print(f"Data OK: {success}, Signal OK: {sig_ok}")
print("PASS" if success and sig_ok else "FAIL")
