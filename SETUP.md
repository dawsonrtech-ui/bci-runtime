# Local Setup

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | 3.14 tested on Ubuntu 26.04 WSL |
| .NET SDK | 8.0+ | Only needed for C# mock tests |
| Unity | 2022.3.29f1 | Only needed for E2E / rebuild |
| WSL (Ubuntu 26.04) | — | Only needed for E2E (Unity Linux build runs under WSL) |

## Quick Start (Python only — no Unity)

```powershell
# Install
pip install -r requirements-dev.txt

# Run SHM unit tests
pytest -v -m "not slow" tests/test_shm_gustation.py tests/test_shm_signal.py tests/test_shm_benchmark.py
```

The Windows-native kernel32 fallback is tested automatically — no bridge DLL needed.

## SHM IPC Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Python Daemon  │ ──→ │  Shared Memory   │ ──→ │  Unity Consumer │
│  (producer)     │     │  (ring buffer)   │     │  (consumer)     │
│                 │ ──→ │  OS Signal       │ ──→ │                 │
│  shm_gustation  │     │  (semaphore /    │     │  ShmNative      │
│  .py            │     │   event)         │     │  Consumer.cs    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Implementation by platform

| Layer | Linux | Windows |
|-------|-------|---------|
| **SHM alloc** | `libbci_bridge.so` via `shm_open`/`mmap` | `mmap(-1, size, tagname=...)` (pure Python) |
| **Signal create** | `libbci_bridge.so` via `sem_open` | kernel32 `CreateEventW` via ctypes |
| **Signal wait** | `libbci_bridge.so` via `sem_wait` / `sem_timedwait` | kernel32 `WaitForSingleObject` via ctypes |
| **Unity SHM** | `libbci_bridge.so` P/Invoke | kernel32 `CreateFileMapping` / `OpenFileMapping` P/Invoke |
| **Unity signal** | `libbci_bridge.so` P/Invoke | kernel32 `CreateEvent` / `OpenEvent` / `WaitForSingleObject` P/Invoke |

The Python side **always prefers the native bridge DLL** and falls back to kernel32 when the DLL is unavailable on Windows. Set `SHM_NO_NATIVE_BRIDGE=1` to force the fallback for testing.

## Running the C# Mock (Windows)

```powershell
# One-time: build, then run the cross-process test
dotnet build csharp_mock
pytest -v tests/test_csharp_mock.py -m slow
```

## Running the Full E2E (needs Unity Linux build)

```powershell
# 1. Rebuild the Unity consumer (requires Unity Editor installed)
./tools/rebuild_unity.sh

# 2. Run the E2E tests under WSL
wsl -d Ubuntu -- bash -c "
  cd /mnt/d/projects/bci-runtime
  python3 -m pytest tests/test_e2e_integration.py -v -m slow
"
```

Two startup orders are verified:
- **producer-first**: Python creates SHM + signal, then Unity attaches with `sig=True`
- **unity-first**: Unity starts, polls for SHM, acquires signal via late-binding (retried every loop cycle)

## Test Reference

| Test file | Count | Marks | What it covers |
|-----------|-------|-------|----------------|
| `test_shm_gustation.py` | 6 | fast | Struct layout, producer/consumer round-trip, ring overflow |
| `test_shm_signal.py` | 5 | fast | Create/open/trigger/wait/timeout, empty→non-empty reactive trigger |
| `test_shm_benchmark.py` | 4 | fast | Throughput (200 Hz), wake latency, kernel transition profile |
| `test_e2e_integration.py` | 2 | slow | Producer-first E2E, Unity-first (late-binding) E2E |
| `test_csharp_mock.py` | 2 | slow | C# mock build + cross-process Python→C# flow |
