# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# Collect all core and board submodules
core_dir = Path("core")
board_dir = Path("board")
tests_dir = Path("tests")

a = Analysis(
    ["daemon_entry.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("daemon_config.json", "."),
        ("core/*.py", "core"),
        ("board/*.py", "board"),
    ],
    hiddenimports=[
        "numba",
        "numba.core",
        "numba.np",
        "numba.np.linalg",
        "scipy.linalg",
        "scipy.linalg.cython_blas",
        "scipy.linalg.cython_lapack",
        "zmq",
        "zmq.backend.cython",
        "brainflow",
        "brainflow.board_shim",
        "brainflow.board_ids",
        "core",
        "core.orchestrator",
        "core.streaming_covariance",
        "core.riemannian",
        "core.spatial_filter",
        "core.artifact_rejection",
        "core.cect",
        "core.voting_ensemble",
        "core.manifold_alignment",
        "core.network_gateway",
        "core.profile_manager",
        "board.base",
        "board.openbci",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PIL",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "jedi",
        "pandas",
        "notebook",
        "pip",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="bci-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
