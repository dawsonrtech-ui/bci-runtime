"""Check if Unity can find the signal - test P/Invoke directly"""
import subprocess, time, sys, os

unity_path = "/mnt/d/projects/bci-runtime/unity-build/BCIConsumer.x86_64"
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import ShmGustationProducer, GustationChannel, SIGNAL_NAME

# Fresh log + clean slate
subprocess.run(["rm", "-f", "/tmp/unity_sig_check.log"])
for target in [f"/dev/shm/Local_BCI_GustationRing", f"/dev/shm/sem.Local_BCI_GustationWake"]:
    if os.path.exists(target):
        os.remove(target)

# Create producer FIRST (before Unity) - creates SHM + signal
producer = ShmGustationProducer()
producer.open()
print(f"Producer open - handle={producer._shm_signal}")

# Now start Unity (SHM and signal already exist)
proc = subprocess.Popen(
    [unity_path, "-nographics", "-batchmode", "-logFile", "/tmp/unity_sig_check.log"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
print(f"Unity PID={proc.pid}")

# Wait for attach
for _ in range(100):
    r = subprocess.run(["grep", "Attached", "/tmp/unity_sig_check.log"],
                       capture_output=True, text=True)
    if r.stdout.strip():
        print(f"Unity: {r.stdout.strip()}")
        break
    time.sleep(0.2)
else:
    print("No Attach message found")

# Write some frames
ch = [GustationChannel(0, 0.5, 50, 1, (0,0,0))]
for pid in range(10):
    producer.write_frame(pid, ch)

time.sleep(1)
print(f"Metrics: {producer.get_metrics()}")
producer.close()
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
    print("Killed Unity")

print("Done")
