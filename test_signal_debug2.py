import sys
sys.path.insert(0, "/mnt/d/projects/bci-runtime")
from core.native_bridge import _find_lib
p = _find_lib()
print("_find_lib:", repr(p))

import ctypes
try:
    lib = ctypes.CDLL(p)
    print("CDLL OK")
    lib.create_os_signal.argtypes = [ctypes.c_char_p]
    lib.create_os_signal.restype = ctypes.c_void_p
    print("argtypes OK")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    import traceback
    traceback.print_exc()
