#!/usr/bin/env bash
# Project Synapse — Unix native build script
# Builds libbci_core.so for both x86_64 and ARM64 targets
#
# Usage:
#   ./build_unix.sh                     # host-native build
#   ./build_unix.sh --all               # all targets (requires cross toolchains)
#   ./build_unix.sh --android           # Android ARM64 via NDK
#   ./build_unix.sh --visionos          # Apple Vision Pro via Xcode
#   ./build_unix.sh clean               # remove build artifacts

set -euo pipefail

SRC="src/bci_core.cpp"
BUILD="build"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$BUILD"

clean() {
    rm -rf "$BUILD"
    echo "Cleaned."
}

build_host() {
    echo "=== Host-native build ==="
    g++ -O3 -fPIC -shared -std=c++17 -fopenmp \
        "$SCRIPT_DIR/$SRC" -o "$BUILD/libbci_core.so"
    echo "  -> $BUILD/libbci_core.so ($(stat -f%z "$BUILD/libbci_core.so" 2>/dev/null || stat -c%s "$BUILD/libbci_core.so") bytes)"
}

build_android() {
    echo "=== Android ARM64 (Meta Quest / Standalone XR) ==="
    local NDK=${ANDROID_NDK_HOME:-$HOME/Android/Sdk/ndk/*/toolchains/llvm/prebuilt/linux-x86_64}
    local TOOLCHAIN=$(echo $NDK | tr ' ' '\n' | sort -V | tail -1)
    if [ ! -d "$TOOLCHAIN" ]; then
        echo "  SKIP: ANDROID_NDK_HOME not set or not found at $NDK"
        return
    fi
    mkdir -p "$BUILD/android-arm64"
    ${TOOLCHAIN}/bin/aarch64-linux-android21-g++ \
        -O3 -fPIC -shared -std=c++17 -static-libstdc++ \
        "$SCRIPT_DIR/$SRC" -o "$BUILD/android-arm64/libbci_core.so"
    echo "  -> $BUILD/android-arm64/libbci_core.so"
}

build_visionos() {
    echo "=== Apple Vision Pro (visionOS ARM64) ==="
    if ! xcrun --sdk xros --show-sdk-path &>/dev/null; then
        echo "  SKIP: visionOS SDK not available (requires Xcode 15.2+)"
        return
    fi
    mkdir -p "$BUILD/visionos-arm64"
    xcrun --sdk xros clang++ -O3 -dynamiclib -arch arm64 -std=c++17 \
        -isysroot $(xcrun --sdk xros --show-sdk-path) \
        "$SCRIPT_DIR/$SRC" -o "$BUILD/visionos-arm64/libbci_core.dylib"
    echo "  -> $BUILD/visionos-arm64/libbci_core.dylib"
}

case "${1:-host}" in
    clean) clean ;;
    --all) build_host; build_android; build_visionos ;;
    --android) build_android ;;
    --visionos) build_visionos ;;
    host|*) build_host ;;
esac
