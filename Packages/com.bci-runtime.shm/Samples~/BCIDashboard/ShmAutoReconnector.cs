using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

public class ShmAutoReconnector : MonoBehaviour
{
    [Header("SHM Config")]
    public string shmName = "";
    public int maxChannels = 0;
    public int pollIntervalMs = 4;
    public float heartbeatTimeoutSec = 3f;

    public string EffectiveShmName => string.IsNullOrEmpty(shmName) ? ShmConfig.ShmName : shmName;
    public int EffectiveMaxChannels => maxChannels > 0 ? maxChannels : ShmConfig.MaxChannels;

    [Header("Status")]
    public bool IsConnected = false;
    public long HeartbeatCount = 0;
    public long FramesRead = 0;

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
    private float[][] _bufferPool;
    private int _poolIdx;
    private readonly byte[] _readBuf4 = new byte[4];

    void Start()
    {
        _bufferPool = new float[EffectiveMaxChannels + 4][];
        for (int i = 0; i < _bufferPool.Length; i++)
            _bufferPool[i] = new float[EffectiveMaxChannels];
        _poolIdx = 0;
        TryConnect();
    }

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

        if (IsConnected && now - _lastFrameArrival > heartbeatTimeoutSec && _inbox.IsEmpty)
        {
            Debug.LogWarning("[SHM] Producer stalled, reconnecting...");
            Disconnect();
            IsConnected = false;
            OnDisconnected?.Invoke();
        }

        if (!IsConnected)
        {
            if (_shmBase == IntPtr.Zero)
                TryConnect();
            return;
        }

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
        _hMap = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, EffectiveShmName);
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
        int slotStride = chHeader + EffectiveMaxChannels * chStride;

        while (_running)
        {
            if (_shmBase == IntPtr.Zero) { Thread.Sleep(100); continue; }

            try
            {
                long hb = Marshal.ReadInt64(_shmBase, 0);
                if (hb == _lastHeartbeat) { Thread.Sleep(pollIntervalMs); continue; }
                _lastHeartbeat = hb; HeartbeatCount++;
                long head = Marshal.ReadInt64(_shmBase, 8);
                long tail = Marshal.ReadInt64(_shmBase, 16);

                while (tail < head)
                {
                    long slotIdx = tail & (RingSize - 1);
                    IntPtr slotAddr = IntPtr.Add(_shmBase, HeaderSize + (int)slotIdx * slotStride);
                    uint chCount = (uint)Marshal.ReadInt32(slotAddr, 4);
                    IntPtr chanBase = IntPtr.Add(slotAddr, chHeader);
                    float[] intensities = _bufferPool[_poolIdx % _bufferPool.Length];
                    _poolIdx++;
                    for (int i = 0; i < (int)chCount && i < EffectiveMaxChannels; i++)
                    {
                        Marshal.Copy(IntPtr.Add(chanBase, i * chStride + 4), _readBuf4, 0, 4);
                        intensities[i] = BitConverter.ToSingle(_readBuf4, 0);
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
