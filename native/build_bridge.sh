#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$SCRIPT_DIR/build"
gcc -O3 -fPIC -shared -std=c11 -D_GNU_SOURCE -lrt \
    "$SCRIPT_DIR/src/bci_bridge.c" "$SCRIPT_DIR/src/shm_signal.c" "$SCRIPT_DIR/src/shm_access.c" \
    -o "$SCRIPT_DIR/build/libbci_bridge.so" -lm -lpthread 2>&1
echo "BUILD EXIT: $?"
ls -la "$SCRIPT_DIR/build/libbci_bridge.so"
nm -D "$SCRIPT_DIR/build/libbci_bridge.so" | grep -E '(open_shm|map_shm|unmap_shm|close_shm|create_os|open_os|trigger|wait_os|close_os)'
