"""Quick check: does Unity see the signal?"""
import subprocess, time, sys, os

unity_path = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import ShmGustationProducer, ShmGustationConsumer

# Fresh log
subprocess.run(["rm", "-f", "/tmp/unity_e2e_sig.log"])

# Clean stale
for target in [f"/dev/shm/Local_BCI_GustationRing", f"/dev/shm/sem.Local_BCI_GustationWake"]:
    if os.path.exists(target):
        os.remove(target)

# Start Unity
proc = subprocess.Popen(
    [unity_path, "-nographics", "-batchmode", "-logFile", "/tmp/unity_e2e_sig.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
time.sleep(2)

# Create producer (creates SHM + signal)
producer = ShmGustationProducer()
producer.open()

# Wait for Unity to attach
for _ in range(100):
    r = subprocess.run(["grep", "Attached", "/tmp/unity_e2e_sig.log"],
                       capture_output=True, text=True)
    if r.stdout:
        print(f"Unity log: {r.stdout.strip()}")
        break
    time.sleep(0.2)
else:
    print("Unity didn't attach within timeout")

# Write frames
ch = [type(sys).__import__('core.shm_gustation').GustationChannel(0, 0.5, 50, 1, (0,0,0))]
for pid in range(20):
    producer.write_frame(pid, ch)

time.sleep(1)
print(f"Metrics: {producer.get_metrics()}")
producer.close()
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

print("Done")
