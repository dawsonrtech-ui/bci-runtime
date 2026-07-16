PLUGIN="/mnt/d/projects/bci-runtime/unity-build/BCIConsumer_Data/Plugins/x86_64/libbci_bridge.so"
SRC="/mnt/d/projects/bci-runtime/native/build/libbci_bridge.so"
echo "=== Unity build plugin ==="
ls -la "$PLUGIN"
nm -D "$PLUGIN" 2>&1 | grep -E 'open_shm|os_signal|map_shm'
echo "=== Source build ==="
ls -la "$SRC"
nm -D "$SRC" 2>&1 | grep -E 'open_shm|os_signal|map_shm'
