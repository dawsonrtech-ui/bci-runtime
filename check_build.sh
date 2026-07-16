echo "=== Source file ==="
ls -la /root/unity-ipc-test/Assets/BCIRuntime/ShmNativeConsumer.cs
echo "=== Build DLL ==="
ls -la /root/unity-ipc-test/build/BCIConsumer_Data/Managed/Assembly-CSharp.dll
echo "=== DLL string check ==="
strings /root/unity-ipc-test/build/BCIConsumer_Data/Managed/Assembly-CSharp.dll | grep -i "signal\|acquired\|late"
echo "=== Build log compilation ==="
grep -i "compil\|error\|ShmNative" /tmp/unity_build3.log 2>&1 | head -5
echo "=== Build log tail ==="
tail -3 /tmp/unity_build3.log
