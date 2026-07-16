"""Test cross-process signal: Python creates, separate subprocess opens and waits."""
import subprocess, sys, time

sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.native_bridge import _find_lib
import ctypes

path = _find_lib()
lib = ctypes.CDLL(path)
lib.create_os_signal.argtypes = [ctypes.c_char_p]
lib.create_os_signal.restype = ctypes.c_void_p
lib.open_os_signal.argtypes = [ctypes.c_char_p]
lib.open_os_signal.restype = ctypes.c_void_p
lib.trigger_os_signal.argtypes = [ctypes.c_void_p]
lib.trigger_os_signal.restype = None
lib.wait_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.wait_os_signal.restype = ctypes.c_int
lib.close_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.close_os_signal.restype = None

NAME = b"Local_BCI_CrossProcTest"

# Create signal
sig = lib.create_os_signal(NAME)
print(f"Created signal handle={sig}")

# Start subprocess that opens and waits
code = (
    "import ctypes, sys\n"
    "sys.path.insert(0, '/mnt/d/projects/bci-runtime')\n"
    "from core.native_bridge import _find_lib\n"
    "lib = ctypes.CDLL(_find_lib())\n"
    "lib.open_os_signal.argtypes = [ctypes.c_char_p]\n"
    "lib.open_os_signal.restype = ctypes.c_void_p\n"
    "lib.wait_os_signal.argtypes = [ctypes.c_void_p, ctypes.c_int]\n"
    "lib.wait_os_signal.restype = ctypes.c_int\n"
    f"h = lib.open_os_signal(b'{NAME.decode()}')\n"
    "print(f'Subproc open: handle={h}')\n"
    "if h:\n"
    "    rc = lib.wait_os_signal(h, 3000)\n"
    "    print(f'Subproc wait: {rc}')\n"
    "else:\n"
    "    print('Subproc: OPEN FAILED')\n"
)

proc = subprocess.Popen(["python3", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(0.5)

# Trigger the signal
print("Parent: triggering signal...")
lib.trigger_os_signal(sig)
time.sleep(0.3)

proc.terminate()
stdout, _ = proc.communicate(timeout=3)
print("Subprocess output:")
print(stdout.decode(errors="replace"))

lib.close_os_signal(sig, NAME)
print("Done")
