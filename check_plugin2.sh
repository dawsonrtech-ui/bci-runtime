PLUGIN="/mnt/d/projects/bci-runtime/unity-build/BCIConsumer_Data/Plugins/libbci_bridge.so"
echo "=== Plugin size ==="
ls -la "$PLUGIN"
echo "=== Plugin symbols ==="
nm -D "$PLUGIN" 2>&1 | grep -E 'open_shm|os_signal|close_sig'
echo "=== Source build symbols ==="
nm -D /mnt/d/projects/bci-runtime/native/build/libbci_bridge.so 2>&1 | grep -E 'open_shm|os_signal|close_sig'
