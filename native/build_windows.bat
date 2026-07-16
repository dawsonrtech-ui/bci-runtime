@echo off
REM Project Synapse — Windows native build script
REM Requires: Visual Studio 2022+ with "Desktop development with C++" workload
REM
REM Usage:
REM   build_windows.bat          — default Release build
REM   build_windows.bat debug    — Debug build (no optimizations, full symbols)

setlocal enabledelayedexpansion

if "%1"=="debug" (
    set OPT=/Od /Zi
    set SUFFIX=d
) else (
    set OPT=/O2
    set SUFFIX=
)

if not exist build mkdir build

echo === Compiling bci_core.cpp (target: x64 Windows) ===
cl %OPT% /std:c++17 /W4 /WX /LD src\bci_core.cpp /Febuild\bci_core%SUFFIX%.dll /link /NOLOGO

if %errorlevel% neq 0 (
    echo FAILED: Compilation error.
    exit /b %errorlevel%
)

echo === Build complete ===
echo   Output: build\bci_core%SUFFIX%.dll
echo   Import lib: build\bci_core%SUFFIX%.lib
echo   Size: 
dir build\bci_core%SUFFIX%.dll | find "."

exit /b 0
