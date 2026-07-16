"""Setup for bci-runtime — custom build commands for native bridge compilation.

pyproject.toml is the primary config; this file only provides the
custom build_ext command that compiles libbci_bridge during install.
"""

import os
import subprocess
import sys
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext

NATIVE_DIR = os.path.join(os.path.dirname(__file__), "native")


class BciNativeBuild(build_ext):
    """Compile the C bridge library before building the wheel."""

    def run(self):
        print(f"[bci-runtime] Compiling native bridge in: {NATIVE_DIR}")
        targets = {"win32": ("bci_bridge.dll", "host"),
                   "darwin": ("libbci_bridge.dylib", "macos-arm64")}
        ext, make_target = targets.get(sys.platform, ("libbci_bridge.so", "host"))

        try:
            subprocess.check_call(
                ["make", make_target],
                cwd=NATIVE_DIR,
                stdout=None if os.environ.get("BCI_VERBOSE") else subprocess.DEVNULL,
            )
            build_dir = os.path.join(NATIVE_DIR, "build")
            found = [t for t in [ext] if os.path.isfile(os.path.join(build_dir, t))]
            if found:
                print(f"[bci-runtime] Compiled: {found[0]}")
            else:
                print(f"[bci-runtime] WARNING: make succeeded but {ext} not found")
        except Exception as exc:
            print(f"[bci-runtime] WARNING: Native compilation skipped ({exc})")
            print("[bci-runtime] Falling back to pure-Python SHM (kernel32 on Windows, native bridge unavailable on Linux)")


setup(
    ext_modules=[Extension("native._bridge", sources=[])],
    cmdclass={"build_ext": BciNativeBuild},
)
