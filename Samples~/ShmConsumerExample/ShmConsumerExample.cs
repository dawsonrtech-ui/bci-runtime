using UnityEngine;
using UnityEngine.UI;
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

/// <summary>
/// Reference closed-loop BCI consumer.
///
/// Reads the SHM ring buffer written by examples/bci_closed_loop.py,
/// extracts bandpower from each channel, and drives Canvas UI elements.
///
/// Attach this to a GameObject with a Canvas child containing:
///   - 8 x Image bars named "Band0".."Band7" (bars scale Y by intensity)
///   - 1 x Text named "HeartbeatLabel" (shows heartbeat + frame rate)
///   - 1 x Text named "LatencyLabel"   (shows wake-to-dequeue latency)
/// </summary>
public class ShmConsumerExample : MonoBehaviour
{
    [Header("SHM Configuration")]
    public string shmName = "Local_BCI_GustationRing";
    public string signalName = "Local_BCI_GustationWake";
    public int maxChannels = 8;
    public int pollIntervalMs = 4;

    [Header("UI References")]
    public RectTransform[] bandBars = new RectTransform[8];
    public Text heartbeatLabel;
    public Text latencyLabel;

    // ── P/Invoke ────────────────────────────────────────────

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(
        uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(
        IntPtr hFileMappingObject, uint dwDesiredAccess,
        uint dwFileOffsetHigh, uint dwFileOffsetLow,
        UIntPtr dwNumberOfBytesToMap);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr hObject);

    private const uint FILE_MAP_ALL_ACCESS = 0xF001F;
    private const int RingSize = 32;
    private const int HeaderSize = 24;      // matches Python: HB(8)+head(8)+tail(8)
    private const int HeartbeatOffset = 0;
    private const int HeadOffset = 8;
    private const int TailOffset = 16;

    private IntPtr _hMap = IntPtr.Zero;
    private IntPtr _shmBase = IntPtr.Zero;
    private bool _running;
    private ulong _lastHeartbeat;

    private struct FrameData
    {
        public ulong heartbeat;
        public float[] intensities;
    }

    private readonly ConcurrentQueue<FrameData> _inbox = new ConcurrentQueue<FrameData>();

    void Start()
    {
        TryAttach();
    }

    private void TryAttach()
    {
        _hMap = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, shmName);
        if (_hMap == IntPtr.Zero)
        {
            Debug.LogWarning("[BCI-Example] SHM not available, retrying...");
            return;
        }
        _shmBase = MapViewOfFile(_hMap, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
        if (_shmBase == IntPtr.Zero)
        {
            CloseHandle(_hMap);
            _hMap = IntPtr.Zero;
            return;
        }
        _running = true;
        Thread worker = new Thread(BackgroundWorker) { IsBackground = true };
        worker.Start();
        Debug.Log("[BCI-Example] Attached to SHM ring buffer");
    }

    private void BackgroundWorker()
    {
        while (_running)
        {
            long hb = Marshal.ReadInt64(_shmBase, HeartbeatOffset);
            if (hb == (long)_lastHeartbeat)
            {
                Thread.Sleep(pollIntervalMs);
                continue;
            }
            _lastHeartbeat = (ulong)hb;

            long head = Marshal.ReadInt64(_shmBase, HeadOffset);
            long tail = Marshal.ReadInt64(_shmBase, TailOffset);

            while (tail < head)
            {
                long slotIdx = tail & (RingSize - 1);
                int slotStride = 8 + maxChannels * 16;
                IntPtr slotAddr = IntPtr.Add(_shmBase, HeaderSize + (int)slotIdx * slotStride);

                uint chCount = (uint)Marshal.ReadInt32(slotAddr, 4);
                IntPtr chanBase = IntPtr.Add(slotAddr, 8);

                float[] intensities = new float[chCount];
                for (int i = 0; i < (int)chCount && i < maxChannels; i++)
                {
                    byte[] b = new byte[4];
                    Marshal.Copy(IntPtr.Add(chanBase, i * 16 + 4), b, 0, 4);
                    intensities[i] = BitConverter.ToSingle(b, 0);
                }

                _inbox.Enqueue(new FrameData
                {
                    heartbeat = _lastHeartbeat,
                    intensities = intensities,
                });

                tail++;
                Marshal.WriteInt64(_shmBase, TailOffset, tail);
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

        while (_inbox.TryDequeue(out FrameData frame))
        {
            // Update band bars
            for (int i = 0; i < frame.intensities.Length && i < bandBars.Length; i++)
            {
                if (bandBars[i] != null)
                {
                    Vector3 scale = bandBars[i].localScale;
                    scale.y = Mathf.Lerp(scale.y, frame.intensities[i] * 2.0f, 0.3f);
                    bandBars[i].localScale = scale;
                }
            }

            // Update labels
            if (heartbeatLabel != null)
                heartbeatLabel.text = $"Heartbeat: {frame.heartbeat}";

            if (latencyLabel != null)
                latencyLabel.text = $"Channels: {frame.intensities.Length}";
        }
    }

    void OnDestroy()
    {
        _running = false;
        if (_shmBase != IntPtr.Zero) { UnmapViewOfFile(_shmBase); _shmBase = IntPtr.Zero; }
        if (_hMap != IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; }
    }
}
