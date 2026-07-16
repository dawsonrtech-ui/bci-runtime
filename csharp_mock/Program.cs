using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;

class Program
{
    // ── Exact binary layouts matching shm_defs.h (Pack=4) ────

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    struct GustationChannel
    {
        public uint   channel_id;
        public float  intensity;
        public float  duration_ms;
        public byte   chemical_profile;
        private byte  _pad0;
        private byte  _pad1;
        private byte  _pad2;
    }

    struct ProcessedFrame
    {
        public uint              packetId;
        public uint              channelCount;
        public GustationChannel[] channels;
    }

    // ── Constants ──────────────────────────────────────────

    static string ShmName    = "Local_BCI_GustationRing";
    static string SignalName = "Local_BCI_GustationWake";
    const int    RingSize    = 32;
    const int    MaxChannels = 16;
    const uint   SlotSize    = 8 + 16 * 16;  // 264
    const uint   HeaderSize  = 24;  // heartbeat(8) + head(8) + tail(8)

    // ── Shared state ───────────────────────────────────────

    static volatile bool _running = true;
    static readonly ConcurrentQueue<ProcessedFrame> _inbox = new();

    // ── P/Invoke: kernel32 for Windows named mmap ──────────

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr OpenFileMapping(uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr MapViewOfFile(IntPtr hFileMappingObject, uint dwDesiredAccess,
        uint dwFileOffsetHigh, uint dwFileOffsetLow, UIntPtr dwNumberOfBytesToMap);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool CloseHandle(IntPtr hObject);

    // ── P/Invoke: create SHM (creates or opens existing) ────

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr CreateFileMapping(IntPtr hFile, IntPtr lpAttributes,
        uint flProtect, uint dwMaximumSizeHigh, uint dwMaximumSizeLow, string lpName);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern IntPtr CreateEvent(IntPtr lpEventAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool bManualReset,
        [MarshalAs(UnmanagedType.Bool)] bool bInitialState, string lpName);

    // ── P/Invoke: kernel32 signal wait (no bridge DLL needed) ──

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    // ── Entry point ────────────────────────────────────────

    unsafe static int Main(string[] args)
    {
        if (args.Length >= 2)
        {
            ShmName = args[0];
            SignalName = args[1];
        }
        else if (args.Length == 1)
        {
            ShmName = args[0];
        }
        Console.Error.WriteLine("[C# MOCK] Starting...");

        const uint PAGE_READWRITE = 0x04;
        const uint SHM_SIZE       = 8464;

        IntPtr hMap = CreateFileMapping(
            new IntPtr(-1), IntPtr.Zero,
            PAGE_READWRITE,
            0, SHM_SIZE, ShmName);

        IntPtr hSignal = CreateEvent(IntPtr.Zero, false, false, SignalName);

        if (hMap == IntPtr.Zero || hSignal == IntPtr.Zero)
        {
            Console.Error.WriteLine("[FAIL] SHM or signal creation failed");
            return 1;
        }

        IntPtr baseAddr = MapViewOfFile(hMap, 0x0002, 0, 0, UIntPtr.Zero);
        if (baseAddr == IntPtr.Zero)
        {
            Console.Error.WriteLine("[FAIL] MapViewOfFile");
            return 1;
        }

        Console.Error.WriteLine($"[C# MOCK] SHM @ {baseAddr:x}, signal @ {hSignal:x}");

        _ = Task.Run(() => DrainWorker(baseAddr, hSignal));

        Console.Error.WriteLine("[C# MOCK] Listening. Press Ctrl+C to stop.");
        Console.CancelKeyPress += (_, _) => _running = false;

        uint expected = 0;
        int frameCount = 0;
        int idleLoops = 0;
        var sw = new Stopwatch();

        while (_running)
        {
            bool gotAny = false;
            while (_inbox.TryDequeue(out var frame))
            {
                gotAny = true;
                idleLoops = 0;
                sw.Restart();
                sw.Stop();
                double latencyUs = sw.Elapsed.TotalMicroseconds;

                if (frameCount > 0 && frame.packetId != expected + 1)
                    Console.Error.WriteLine($"[SEQ FAULT] expected {expected + 1}, got {frame.packetId}");

                expected = frame.packetId;
                frameCount++;

                string ch0 = frame.channelCount > 0
                    ? $"ch[0]: id={frame.channels[0].channel_id} i={frame.channels[0].intensity:F2} c=#{frame.channels[0].chemical_profile}"
                    : "no channels";

                Console.Out.WriteLine($"[FRAME #{frameCount}] pid={frame.packetId} | "
                    + $"chCount={frame.channelCount} | {ch0} | dequeue={latencyUs:F1} us");
                Console.Out.Flush();
            }

            if (!gotAny)
            {
                idleLoops++;
                if (idleLoops > 300)  // ~3.3 s idle → producer is done
                {
                    Console.Error.WriteLine("[C# MOCK] Idle timeout, shutting down.");
                    break;
                }
            }

            Thread.Sleep(11);
        }

        Console.Error.WriteLine($"\n[C# MOCK] Received {frameCount} frames total. Shutting down...");
        CloseHandle(hSignal);
        UnmapViewOfFile(baseAddr);
        CloseHandle(hMap);
        return 0;
    }

    // ── Background drain worker ─────────────────────────────

    static unsafe void DrainWorker(IntPtr baseAddr, IntPtr hSignal)
    {
        ulong* headPtr = (ulong*)(baseAddr + 8);
        ulong* tailPtr = (ulong*)(baseAddr + 16);

        while (_running)
        {
            ulong head = *headPtr;
            ulong tail = *tailPtr;

            if (tail >= head)
            {
                WaitForSingleObject(hSignal, 100);
                continue;
            }

            while (tail < head)
            {
                ulong slotIdx  = tail & (RingSize - 1);
                IntPtr slotAddr = baseAddr + (int)(HeaderSize + (slotIdx * SlotSize));

                uint packetId     = *(uint*)slotAddr;
                uint channelCount = *(uint*)(slotAddr + 4);
                IntPtr chanBase   = slotAddr + 8;

                var channels = new GustationChannel[channelCount];

                fixed (GustationChannel* dest = channels)
                {
                    Buffer.MemoryCopy(
                        (void*)chanBase, dest,
                        channels.Length * sizeof(GustationChannel),
                        channelCount * sizeof(GustationChannel));
                }

                _inbox.Enqueue(new ProcessedFrame
                {
                    packetId = packetId,
                    channelCount = channelCount,
                    channels = channels,
                });

                tail++;
                *tailPtr = tail;
            }
        }
    }
}
