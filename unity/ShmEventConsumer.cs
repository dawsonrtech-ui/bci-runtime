using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Collections.Concurrent;
using Unity.Collections.LowLevel.Unsafe;

public class ShmEventConsumer : MonoBehaviour
{
    private const string ShmName = "Local_BCI_GustationRing";
    private const string SignalName = "Local_BCI_GustationWake";
    private const int RingSize = 32;
    private const int MaxChannels = 16;

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct GustationChannel
    {
        public uint channelId;
        public float intensity;
        public float durationMs;
        public byte chemicalProfile;
        private byte pad0, pad1, pad2;
    }

    public struct ProcessedFrame
    {
        public uint packetId;
        public uint channelCount;
        public GustationChannel[] channels;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(
        uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(
        IntPtr hFileMappingObject, uint dwDesiredAccess,
        uint dwFileOffsetHigh, uint dwFileOffsetLow,
        UIntPtr dwNumberOfBytesToMap);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    [DllImport("bci_bridge", EntryPoint = "open_os_signal")]
    private static extern IntPtr OpenOsSignal(string name);

    [DllImport("bci_bridge", EntryPoint = "wait_os_signal")]
    private static extern int WaitOsSignal(IntPtr sig, int timeoutMs);

    [DllImport("bci_bridge", EntryPoint = "close_os_signal")]
    private static extern void CloseOsSignal(IntPtr sig, string name);

    private const uint FILE_MAP_READ = 0x0004;

    [Header("Gustation Event-Driven IPC")]
    public int maxChannels = 16;

    private IntPtr _fileMapping = IntPtr.Zero;
    private IntPtr _shmBase = IntPtr.Zero;
    private IntPtr _wakeSignal = IntPtr.Zero;
    private bool _running = false;
    private uint _slotSize;

    private ConcurrentQueue<ProcessedFrame> _inbox =
        new ConcurrentQueue<ProcessedFrame>();

    public delegate void OnGustationFrameDelegate(
        uint packetId, GustationChannel[] channels, int count);
    public event OnGustationFrameDelegate OnGustationFrame;

    void Start()
    {
        _slotSize = 8 + (uint)MaxChannels *
                    (uint)Marshal.SizeOf<GustationChannel>();
        TryAttach();
    }

    private void TryAttach()
    {
        _fileMapping = OpenFileMapping(FILE_MAP_READ, false, ShmName);
        _wakeSignal = OpenOsSignal(SignalName);

        if (_fileMapping == IntPtr.Zero || _wakeSignal == IntPtr.Zero)
        {
            Debug.LogWarning("[SHM-EVT] Waiting for producer...");
            return;
        }

        _shmBase = MapViewOfFile(
            _fileMapping, FILE_MAP_READ, 0, 0, UIntPtr.Zero);

        if (_shmBase != IntPtr.Zero)
        {
            _running = true;
            Task.Run(() => BackgroundWorker());
            Debug.Log("[SHM-EVT] Background worker started (event-driven)");
        }
    }

    private void BackgroundWorker()
    {
        unsafe
        {
            ulong* headPtr = (ulong*)_shmBase.ToPointer();
            ulong* tailPtr = (ulong*)(_shmBase + 8).ToPointer();
            uint headerSize = 16;

            while (_running)
            {
                ulong head = *headPtr;
                ulong tail = *tailPtr;

                if (tail >= head)
                {
                    WaitOsSignal(_wakeSignal, 100);
                    continue;
                }

                while (tail < head)
                {
                    ulong slotIdx = tail & (RingSize - 1);
                    IntPtr slotAddr = _shmBase + (int)(
                        headerSize + (slotIdx * _slotSize));

                    uint packetId = *(uint*)slotAddr;
                    uint channelCount = *(uint*)(slotAddr + 4);
                    IntPtr chanBase = slotAddr + 8;

                    var frame = new ProcessedFrame
                    {
                        packetId = packetId,
                        channelCount = channelCount,
                        channels = new GustationChannel[channelCount],
                    };

                    fixed (GustationChannel* dest = frame.channels)
                    {
                        UnsafeUtility.MemCpy(dest, (void*)chanBase,
                            channelCount * (uint)Marshal.SizeOf<GustationChannel>());
                    }

                    _inbox.Enqueue(frame);

                    tail++;
                    *tailPtr = tail;
                }
            }
        }
    }

    void Update()
    {
        if (!_running)
        {
            TryAttach();
            return;
        }

        while (_inbox.TryDequeue(out ProcessedFrame frame))
        {
            if (OnGustationFrame != null)
            {
                OnGustationFrame.Invoke(
                    frame.packetId, frame.channels,
                    (int)frame.channelCount);
            }
            TriggerTasteReceptors(frame);
        }
    }

    private void TriggerTasteReceptors(ProcessedFrame frame)
    {
        // Main-thread safe zone: update VR hardware / shader parameters here
        for (int i = 0; i < frame.channelCount; i++)
        {
            var ch = frame.channels[i];
            // ch.channelId, ch.intensity, ch.chemicalProfile available
        }
    }

    void OnDestroy()
    {
        _running = false;
        if (_shmBase != IntPtr.Zero) UnmapViewOfFile(_shmBase);
        if (_fileMapping != IntPtr.Zero) CloseHandle(_fileMapping);
        if (_wakeSignal != IntPtr.Zero) CloseOsSignal(_wakeSignal, SignalName);
    }
}
