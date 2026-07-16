#!/usr/bin/env bash
# Rebuild Unity standalone consumers.
# Requires Unity 2022.3.29f1 installed with:
#   - Linux IL2CPP module
#   - Windows IL2CPP module (for Windows builds)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
UNITY_DIR="$PROJECT_DIR/unity"

UNITY_HUB="${UNITY_HUB:-C:/Program Files/Unity/Hub/Editor}"
UNITY_VER="2022.3.29f1"

if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
    UNITY_EXE="$UNITY_HUB/$UNITY_VER/Editor/Unity.exe"
else
    UNITY_EXE="$UNITY_HUB/$UNITY_VER/Editor/Unity"
fi

if [ ! -f "$UNITY_EXE" ]; then
    echo "Unity not found at $UNITY_EXE"
    echo "Set UNITY_HUB or install Unity $UNITY_VER with IL2CPP modules"
    exit 1
fi

TARGET="${1:-linux-mono}"

case "$TARGET" in
    linux-mono)
        echo "Building Linux Mono standalone..."
        "$UNITY_EXE" -quit -batchmode -projectPath "$UNITY_DIR" \
            -executeMethod BuildPlayer.BuildLinuxMono \
            -logFile "$PROJECT_DIR/unity_build_mono.log"
        echo "Log: $PROJECT_DIR/unity_build_mono.log"
        ;;
    linux-il2cpp)
        echo "Building Linux IL2CPP standalone..."
        "$UNITY_EXE" -quit -batchmode -projectPath "$UNITY_DIR" \
            -executeMethod BuildPlayer.BuildLinuxIL2CPP \
            -logFile "$PROJECT_DIR/unity_build_il2cpp.log"
        echo "Log: $PROJECT_DIR/unity_build_il2cpp.log"
        ;;
    windows-il2cpp)
        echo "Building Windows IL2CPP standalone..."
        "$UNITY_EXE" -quit -batchmode -projectPath "$UNITY_DIR" \
            -executeMethod BuildPlayer.BuildWindowsIL2CPP \
            -logFile "$PROJECT_DIR/unity_build_win.log"
        echo "Log: $PROJECT_DIR/unity_build_win.log"
        ;;
    all)
        echo "Building all targets..."
        "$UNITY_EXE" -quit -batchmode -projectPath "$UNITY_DIR" \
            -executeMethod BuildPlayer.BuildAll \
            -logFile "$PROJECT_DIR/unity_build_all.log"
        echo "Log: $PROJECT_DIR/unity_build_all.log"
        ;;
    *)
        echo "Usage: $0 [linux-mono|linux-il2cpp|windows-il2cpp|all]"
        exit 1
        ;;
esac

echo "Done: $TARGET"
