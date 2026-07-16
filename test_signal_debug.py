import os, sys, ctypes

sys.path.insert(0, "/mnt/d/projects/bci-runtime")

# Step 1: check _find_lib
from core.native_bridge import _find_lib
path = _find_lib()
print("_find_lib() path:", repr(path))

# Step 2: try loading
if path:
    try:
        lib = ctypes.CDLL(path)
        print("CDLL loaded OK")
        print(dir(lib))
    except Exception as e:
        print("CDLL failed:", e)
else:
    # Manually search
    for root, dirs, files in os.walk("/mnt/d/projects/bci-runtime/native/build"):
        for f in files:
            print(f"  File: {root}/{f}")
        break  # just top level

# Step 3: try directly
print("\nChecking core path...")
import core.shm_gustation as sg
print("sg file:", sg.__file__)
candidates = [
    os.path.abspath(os.path.join(os.path.dirname(sg.__file__), "..", "native", "build", "bci_bridge.dll")),
    os.path.abspath(os.path.join(os.path.dirname(sg.__file__), "..", "native", "build", "libbci_bridge.so")),
    os.path.abspath(os.path.join(os.path.dirname(sg.__file__), "..", "native", "build", "libbci_bridge.dylib")),
]
for c in candidates:
    print(f"  {c}: exists={os.path.isfile(c)}")
