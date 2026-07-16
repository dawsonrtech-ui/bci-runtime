using UnityEngine;
using System;
using System.Runtime.InteropServices;

public class ShmConsumerBridge : MonoBehaviour
{
    private const string ShmName = "Local_BCI_GustationRing";
    private const int RingSize = 32;
    private const int MaxChannels = 16;
    private const int SlotMask = RingSize - 1;

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct GustationChannel
    {
        public uint channelId;
        public float intensity;
        public float durationMs;
        public byte chemicalProfile;
        private byte pad0, pad1, pad2;
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct ShmSlot
    {
        public uint packetId;
        public uint channelCount;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = MaxChannels)]
        public GustationChannel[] channels;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct SharedRingBuffer
    {
        public ulong head;
        public ulong tail;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = RingSize)]
        public ShmSlot[] slots;
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

    private const uint FILE_MAP_READ = 0x0004;

    [Header("Gustation IPC")]
    public int frameInterval = 1;

    private IntPtr _fileMapping = IntPtr.Zero;
    private IntPtr _shmBase = IntPtr.Zero;
    private int _headerSize = 16;
    private int _slotSize;
    private int _framesSkipped;

    public delegate void OnGustationFrameDelegate(
        uint packetId, GustationChannel[] channels, int count);
    public event OnGustationFrameDelegate OnGustationFrame;

    void Start()
    {
        _slotSize = Marshal.SizeOf<ShmSlot>();
        TryAttach();
    }

    private void TryAttach()
    {
        _fileMapping = OpenFileMapping(FILE_MAP_READ, false, ShmName);
        if (_fileMapping == IntPtr.Zero)
        {
            Debug.LogWarning("[SHM] Producer not yet available, will retry...");
            return;
        }

        _shmBase = MapViewOfFile(
            _fileMapping, FILE_MAP_READ, 0, 0, UIntPtr.Zero);

        if (_shmBase == IntPtr.Zero)
        {
            Debug.LogError("[SHM] MapViewOfFile failed");
            CloseHandle(_fileMapping);
            _fileMapping = IntPtr.Zero;
        }
        else
        {
            Debug.Log("[SHM] Consumer attached to ring buffer");
        }
    }

    void Update()
    {
        if (_shmBase == IntPtr.Zero)
        {
            TryAttach();
            return;
        }

        unsafe
        {
            ulong* headPtr = (ulong*)_shmBase.ToPointer();
            ulong* tailPtr = (ulong*)(_shmBase + 8).ToPointer();

            ulong head = *headPtr;
            ulong tail = *tailPtr;

            while (tail < head)
            {
                ulong slotIdx = tail & SlotMask;
                IntPtr slotAddr = _shmBase + _headerSize
                                  + (int)(slotIdx * _slotSize);

                uint packetId = *(uint*)slotAddr;
                uint channelCount = *(uint*)(slotAddr + 4);

                GustationChannel[] channels = new GustationChannel[channelCount];
                IntPtr chanBase = slotAddr + 8;
                for (int i = 0; i < channelCount; i++)
                {
                    channels[i] = (GustationChannel)Marshal.PtrToStructure(
                        chanBase + i * Marshal.SizeOf<GustationChannel>(),
                        typeof(GustationChannel));
                }

                if (OnGustationFrame != null)
                {
                    OnGustationFrame.Invoke(
                        packetId, channels, (int)channelCount);
                }

                tail++;
                *tailPtr = tail;
            }
        }
    }

    void OnDestroy()
    {
        if (_shmBase != IntPtr.Zero) UnmapViewOfFile(_shmBase);
        if (_fileMapping != IntPtr.Zero) CloseHandle(_fileMapping);
    }
}
