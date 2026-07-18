using UnityEngine;
using System.IO;
using System.Text.RegularExpressions;

public static class ShmConfig
{
    private static bool _loaded;
    private static string _shmName = "Local_BCI_GustationRing";
    private static string _returnShmName = "Local_BCI_GustationRing_Return";
    private static int _ringBufferSize = 32;
    private static int _maxChannels = 8;
    private static int _headerSize = 24;
    private static int _returnRingSize = 8;

    public static string ShmName { get { Load(); return _shmName; } }
    public static string ReturnShmName { get { Load(); return _returnShmName; } }
    public static int RingBufferSize { get { Load(); return _ringBufferSize; } }
    public static int MaxChannels { get { Load(); return _maxChannels; } }
    public static int HeaderSize { get { Load(); return _headerSize; } }
    public static int ReturnRingSize { get { Load(); return _returnRingSize; } }

    static void Load()
    {
        if (_loaded) return;
        _loaded = true;

        string path = Path.Combine(Application.streamingAssetsPath, "shm_config.json");
        if (!File.Exists(path)) return;

        try
        {
            string json = File.ReadAllText(path);
            var m = Regex.Match(json, "\"shm_name\"\\s*:\\s*\"([^\"]+)\"");
            if (m.Success) _shmName = m.Groups[1].Value;
            m = Regex.Match(json, "\"return_shm_name\"\\s*:\\s*\"([^\"]+)\"");
            if (m.Success) _returnShmName = m.Groups[1].Value;
            m = Regex.Match(json, "\"ring_buffer_size\"\\s*:\\s*(\\d+)");
            if (m.Success) _ringBufferSize = int.Parse(m.Groups[1].Value);
            m = Regex.Match(json, "\"max_channels\"\\s*:\\s*(\\d+)");
            if (m.Success) _maxChannels = int.Parse(m.Groups[1].Value);
            m = Regex.Match(json, "\"header_size\"\\s*:\\s*(\\d+)");
            if (m.Success) _headerSize = int.Parse(m.Groups[1].Value);
            m = Regex.Match(json, "\"return_ring_buffer_size\"\\s*:\\s*(\\d+)");
            if (m.Success) _returnRingSize = int.Parse(m.Groups[1].Value);
        }
        catch { }
    }
}
