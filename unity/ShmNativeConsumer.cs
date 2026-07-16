using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

public class ShmNativeConsumer : MonoBehaviour
{
#if UNITY_STANDALONE_WIN
    private const string ShmName = "Local_BCI_GustationRing";
    private const string SignalName = "Local_BCI_GustationWake";
#else
    private const string ShmName = "/Local_BCI_GustationRing";
    private const string SignalName = "/Local_BCI_GustationWake";
#endif

    private const int RingSize = 32;
    private const int MaxChannels = 16;
    private const int HeaderSize = 24;  // heartbeat(8) + head(8) + tail(8)
    private const int HeartbeatOffset = 0;
    private const int HeadOffset = 8;
    private const int TailOffset = 16;

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

#if UNITY_STANDALONE_WIN
    // ── Windows kernel32 P/Invoke (no bridge DLL needed) ──

    private const uint PAGE_READWRITE = 0x04;
    private const uint FILE_MAP_ALL_ACCESS = 0xF001F;
    private const uint EVENT_MODIFY_STATE = 0x0002;
    private const uint SYNCHRONIZE = 0x00100000;
    private const uint INFINITE = 0xFFFFFFFF;

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr CreateFileMapping(IntPtr hFile, IntPtr lpAttributes,
        uint flProtect, uint dwMaximumSizeHigh, uint dwMaximumSizeLow, string lpName);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(IntPtr hFileMappingObject, uint dwDesiredAccess,
        uint dwFileOffsetHigh, uint dwFileOffsetLow, UIntPtr dwNumberOfBytesToMap);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr hObject);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr CreateEvent(IntPtr lpEventAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool bManualReset,
        [MarshalAs(UnmanagedType.Bool)] bool bInitialState, string lpName);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenEvent(uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetEvent(IntPtr hEvent);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    private IntPtr _shmHandle = IntPtr.Zero;
#else
    // ── Linux bci_bridge DLL P/Invoke ──

    [DllImport("bci_bridge", EntryPoint = "open_shm")]
    private static extern int OpenShm(string name, int size, int create);

    [DllImport("bci_bridge", EntryPoint = "map_shm")]
    private static extern IntPtr MapShm(int fd, int size);

    [DllImport("bci_bridge", EntryPoint = "unmap_shm")]
    private static extern void UnmapShm(IntPtr ptr, int size);

    [DllImport("bci_bridge", EntryPoint = "close_shm")]
    private static extern void CloseShm(int fd, string name, int destroy);

    [DllImport("bci_bridge", EntryPoint = "open_os_signal")]
    private static extern IntPtr OpenOsSignal(string name);

    [DllImport("bci_bridge", EntryPoint = "wait_os_signal")]
    private static extern int WaitOsSignal(IntPtr sig, int timeoutMs);

    [DllImport("bci_bridge", EntryPoint = "close_os_signal")]
    private static extern void CloseOsSignal(IntPtr sig, string name);

    private int _shmFd = -1;
#endif

    public int maxChannels = 16;
    public int pollIntervalMs = 5;

    private IntPtr _shmBase = IntPtr.Zero;
    private IntPtr _wakeSignal = IntPtr.Zero;
    private int _shmSize;
    private int _slotSize;
    private bool _running;

    private ConcurrentQueue<ProcessedFrame> _inbox = new ConcurrentQueue<ProcessedFrame>();

    public delegate void OnGustationFrameDelegate(uint packetId, GustationChannel[] channels, int count);
    public event OnGustationFrameDelegate OnGustationFrame;

    void Start()
    {
        _slotSize = 8 + maxChannels * Marshal.SizeOf<GustationChannel>();
        _shmSize = HeaderSize + RingSize * _slotSize;
        TryAttach();
    }

    private void TryAttach()
    {
#if UNITY_STANDALONE_WIN
        if (_shmHandle == IntPtr.Zero)
        {
            _shmHandle = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, ShmName);
            if (_shmHandle == IntPtr.Zero)
                _shmHandle = CreateFileMapping(new IntPtr(-1), IntPtr.Zero,
                    PAGE_READWRITE, 0, (uint)_shmSize, ShmName);
        }
        if (_wakeSignal == IntPtr.Zero)
            _wakeSignal = OpenEvent(EVENT_MODIFY_STATE | SYNCHRONIZE, false, SignalName);
        if (_shmBase == IntPtr.Zero && _shmHandle != IntPtr.Zero)
            _shmBase = MapViewOfFile(_shmHandle, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
#else
        if (_shmFd < 0)
            _shmFd = OpenShm(ShmName, _shmSize, 0);
        if (_wakeSignal == IntPtr.Zero)
            _wakeSignal = OpenOsSignal(SignalName);
        if (_shmBase == IntPtr.Zero && _shmFd >= 0)
            _shmBase = MapShm(_shmFd, _shmSize);
#endif

        if (_shmBase == IntPtr.Zero)
        {
            Debug.LogWarning("[SHM] Producer not available, retrying...");
            return;
        }

        _running = true;
        Thread worker = new Thread(BackgroundWorker);
        worker.IsBackground = true;
        worker.Start();
        Debug.Log($"[SHM] Attached (sig={_wakeSignal != IntPtr.Zero})");
    }

    private void BackgroundWorker()
    {
        unsafe
        {
            ulong* heartbeatPtr = (ulong*)_shmBase.ToPointer();
            ulong* headPtr = (ulong*)(_shmBase + HeadOffset).ToPointer();
            ulong* tailPtr = (ulong*)(_shmBase + TailOffset).ToPointer();
            ulong lastHeartbeat = 0;

            while (_running)
            {
                if (_wakeSignal == IntPtr.Zero)
                {
                    _wakeSignal = TryOpenSignal();
                    if (_wakeSignal != IntPtr.Zero)
                        Debug.Log("[SHM] Signal acquired (late-binding)");
                }

                ulong hb = *heartbeatPtr;
                if (hb == lastHeartbeat)
                {
                    Thread.Sleep(pollIntervalMs);
                    continue;
                }
                lastHeartbeat = hb;

                ulong head = *headPtr;
                ulong tail = *tailPtr;

                if (tail >= head)
                {
                    if (_wakeSignal != IntPtr.Zero)
                        TryWaitSignal(_wakeSignal, pollIntervalMs);
                    else
                        Thread.Sleep(pollIntervalMs);
                    continue;
                }

                while (tail < head)
                {
                    ulong slotIdx = tail & (RingSize - 1);
                    IntPtr slotAddr = _shmBase + HeaderSize + (int)((long)slotIdx * _slotSize);

                    uint packetId = *(uint*)slotAddr;
                    uint channelCount = *(uint*)(slotAddr + 4);
                    IntPtr chanBase = slotAddr + 8;

                    var frame = new ProcessedFrame
                    {
                        packetId = packetId,
                        channelCount = channelCount,
                        channels = new GustationChannel[channelCount],
                    };

                    for (int i = 0; i < channelCount; i++)
                    {
                        frame.channels[i] = (GustationChannel)Marshal.PtrToStructure(
                            chanBase + i * Marshal.SizeOf<GustationChannel>(),
                            typeof(GustationChannel));
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
            OnGustationFrame?.Invoke(frame.packetId, frame.channels, (int)frame.channelCount);
        }
    }

    void OnDestroy()
    {
        _running = false;
#if UNITY_STANDALONE_WIN
        if (_shmBase != IntPtr.Zero) { UnmapViewOfFile(_shmBase); _shmBase = IntPtr.Zero; }
        if (_shmHandle != IntPtr.Zero) { CloseHandle(_shmHandle); _shmHandle = IntPtr.Zero; }
#else
        if (_shmBase != IntPtr.Zero) { UnmapShm(_shmBase, _shmSize); _shmBase = IntPtr.Zero; }
        if (_shmFd >= 0) { CloseShm(_shmFd, ShmName, 0); _shmFd = -1; }
#endif
        if (_wakeSignal != IntPtr.Zero) { TryCloseSignal(_wakeSignal); _wakeSignal = IntPtr.Zero; }
    }

    // ── Platform-abstracted helpers ──

    private IntPtr TryOpenSignal()
    {
#if UNITY_STANDALONE_WIN
        return OpenEvent(EVENT_MODIFY_STATE | SYNCHRONIZE, false, SignalName);
#else
        return OpenOsSignal(SignalName);
#endif
    }

    private void TryWaitSignal(IntPtr sig, int timeoutMs)
    {
#if UNITY_STANDALONE_WIN
        WaitForSingleObject(sig, timeoutMs < 0 ? INFINITE : (uint)timeoutMs);
#else
        WaitOsSignal(sig, timeoutMs);
#endif
    }

    private void TryCloseSignal(IntPtr sig)
    {
#if UNITY_STANDALONE_WIN
        CloseHandle(sig);
#else
        CloseOsSignal(sig, SignalName);
#endif
    }
}
