using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Text;

public class ShmReturnWriter : IDisposable
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(uint dwDesiredAccess, bool bInheritHandle, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateFileMapping(IntPtr hFile, IntPtr lpAttributes, uint flProtect, uint dwMaximumSizeHigh, uint dwMaximumSizeLow, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(IntPtr hFileMappingObject, uint dwDesiredAccess, uint dwFileOffsetHigh, uint dwFileOffsetLow, UIntPtr dwNumberOfBytesToMap);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr CreateEvent(IntPtr lpEventAttributes, bool bManualReset, bool bInitialState, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetEvent(IntPtr hEvent);

    private const uint PAGE_READWRITE = 0x04;
    private const uint FILE_MAP_ALL_ACCESS = 0xF001F;
    private const int ReturnRingSize = 8;
    private const int ReturnSlotSize = 112;
    private const int ReturnHeaderSize = 16;

    private IntPtr _hMap = IntPtr.Zero;
    private IntPtr _shmBase = IntPtr.Zero;
    private IntPtr _hEvent = IntPtr.Zero;

    public bool Connect()
    {
        int totalSize = ReturnHeaderSize + ReturnRingSize * ReturnSlotSize;
        _hMap = CreateFileMapping(new IntPtr(-1), IntPtr.Zero, PAGE_READWRITE, 0, (uint)totalSize, "Local_BCI_GustationRing_Return");
        if (_hMap == IntPtr.Zero) return false;
        _shmBase = MapViewOfFile(_hMap, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
        if (_shmBase == IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; return false; }
        _hEvent = CreateEvent(IntPtr.Zero, false, false, "Local_BCI_GustationReturn_Wake");
        return true;
    }

    public void SendAck(ulong frameId)
    {
        WriteSlot(frameId, 0, null, null);
    }

    public void SendProcessed(ulong frameId, float[] values)
    {
        WriteSlot(frameId, 1, values, null);
    }

    public void SendCommand(string command)
    {
        WriteSlot(0, 2, null, command);
    }

    private void WriteSlot(ulong ackFrameId, int msgType, float[] values, string command)
    {
        if (_shmBase == IntPtr.Zero) return;
        ulong head = (ulong)Marshal.ReadInt64(_shmBase, 0);
        ulong tail = (ulong)Marshal.ReadInt64(_shmBase, 8);
        if ((head - tail) >= (ulong)ReturnRingSize) return;
        ulong slotIdx = head & (ulong)(ReturnRingSize - 1);
        IntPtr slot = IntPtr.Add(_shmBase, ReturnHeaderSize + (int)slotIdx * ReturnSlotSize);
        Marshal.WriteInt64(slot, 0, (long)ackFrameId);
        Marshal.WriteInt32(slot, 8, msgType);
        int count = values != null ? Mathf.Min(values.Length, 16) : 0;
        Marshal.WriteInt32(slot, 12, count);
        for (int i = 0; i < count; i++)
        {
            byte[] b = BitConverter.GetBytes(values[i]);
            Marshal.Copy(b, 0, IntPtr.Add(slot, 16 + i * 4), 4);
        }
        if (command != null)
        {
            byte[] cmdBytes = Encoding.UTF8.GetBytes(command);
            int len = Mathf.Min(cmdBytes.Length, 31);
            Marshal.Copy(cmdBytes, 0, IntPtr.Add(slot, 80), len);
            Marshal.WriteByte(IntPtr.Add(slot, 80 + len), 0);
        }
        Marshal.WriteInt64(_shmBase, 0, (long)(head + 1));
        if (_hEvent != IntPtr.Zero) SetEvent(_hEvent);
    }

    public void Dispose()
    {
        if (_shmBase != IntPtr.Zero) { UnmapViewOfFile(_shmBase); _shmBase = IntPtr.Zero; }
        if (_hMap != IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; }
        if (_hEvent != IntPtr.Zero) { CloseHandle(_hEvent); _hEvent = IntPtr.Zero; }
    }
}
