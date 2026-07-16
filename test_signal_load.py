import sys
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.shm_gustation import _load_signal_lib, _SIG_LIB
print("_load_signal_lib() result:", _load_signal_lib())
print("_SIG_LIB:", _SIG_LIB)
if _SIG_LIB:
    print("Functions:", [x for x in dir(_SIG_LIB) if "signal" in x or "shm" in x])
