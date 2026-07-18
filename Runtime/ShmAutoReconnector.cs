using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

public class ShmAutoReconnector : MonoBehaviour
{
    [Header("SHM Config")]
    public string shmName = "Local_BCI_GustationRing";
    public int maxChannels = 8;
    public int pollIntervalMs = 4;
    public float heartbeatTimeoutSec = 3f;

    [Header("Status (read only)")]
    public bool IsConnected { get; private set; }
    public long HeartbeatCount { get; private set; }
    public long FramesRead { get; private set; }
    public float LastFrameTime { get; private set; }

    public event Action OnConnected;
    public event Action OnDisconnected;
    public event Action<float[]> OnFrame;

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(uint dwDesiredAccess, bool bInheritHandle, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(IntPtr hFileMappingObject, uint dwDesiredAccess, uint dwFileOffsetHigh, uint dwFileOffsetLow, UIntPtr dwNumberOfBytesToMap);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    private const uint FILE_MAP_ALL_ACCESS = 0xF001F;
    private const int RingSize = 32;
    private const int HeaderSize = 24;

    private IntPtr _hMap = IntPtr.Zero, _shmBase = IntPtr.Zero;
    private long _lastHeartbeat;
    private bool _running;
    private float _lastFrameArrival;
    private ConcurrentQueue<float[]> _inbox = new ConcurrentQueue<float[]>();

    void Start() => TryConnect();

    void OnEnable()
    {
        if (_running) return;
        _running = true;
        new Thread(BackgroundWorker) { IsBackground = true }.Start();
    }

    void OnDisable()
    {
        _running = false;
        Disconnect();
    }

    void Update()
    {
        float now = Time.unscaledTime;

        // Heartbeat check
        if (IsConnected && now - _lastFrameArrival > heartbeatTimeoutSec && _inbox.IsEmpty)
        {
            Debug.LogWarning("[SHM] Producer stalled, reconnecting...");
            Disconnect();
            IsConnected = false;
            OnDisconnected?.Invoke();
        }

        // Auto-reconnect
        if (!IsConnected)
        {
            if (_shmBase == IntPtr.Zero)
                TryConnect();
            return;
        }

        // Drain inbox
        while (_inbox.TryDequeue(out float[] intensities))
        {
            FramesRead++;
            _lastFrameArrival = now;
            OnFrame?.Invoke(intensities);
        }
    }

    void OnDestroy() { _running = false; Disconnect(); }

    public void TryConnect()
    {
        Disconnect();
        _hMap = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, shmName);
        if (_hMap == IntPtr.Zero) return;
        _shmBase = MapViewOfFile(_hMap, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
        if (_shmBase == IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; return; }
        IsConnected = true;
        _lastFrameArrival = Time.unscaledTime;
        OnConnected?.Invoke();
    }

    void Disconnect()
    {
        if (_shmBase != IntPtr.Zero) { UnmapViewOfFile(_shmBase); _shmBase = IntPtr.Zero; }
        if (_hMap != IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; }
    }

    void BackgroundWorker()
    {
        int chHeader = 8, chStride = 16;
        int slotStride = chHeader + maxChannels * chStride;

        while (_running)
        {
            if (_shmBase == IntPtr.Zero) { Thread.Sleep(100); continue; }

            try
            {
                long hb = Marshal.ReadInt64(_shmBase, 0);
                if (hb == _lastHeartbeat) { Thread.Sleep(pollIntervalMs); continue; }
                _lastHeartbeat = hb;
                long head = Marshal.ReadInt64(_shmBase, 8);
                long tail = Marshal.ReadInt64(_shmBase, 16);

                while (tail < head)
                {
                    long slotIdx = tail & (RingSize - 1);
                    IntPtr slotAddr = IntPtr.Add(_shmBase, HeaderSize + (int)slotIdx * slotStride);
                    uint chCount = (uint)Marshal.ReadInt32(slotAddr, 4);
                    IntPtr chanBase = IntPtr.Add(slotAddr, chHeader);
                    float[] intensities = new float[chCount];
                    for (int i = 0; i < (int)chCount && i < maxChannels; i++)
                    {
                        byte[] b = new byte[4];
                        Marshal.Copy(IntPtr.Add(chanBase, i * chStride + 4), b, 0, 4);
                        intensities[i] = BitConverter.ToSingle(b, 0);
                    }
                    _inbox.Enqueue(intensities);
                    tail++;
                    Marshal.WriteInt64(_shmBase, 16, tail);
                }
            }
            catch
            {
                _inbox.Enqueue(null);
            }
        }
    }
}
