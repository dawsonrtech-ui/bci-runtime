using UnityEngine;
using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Collections.Concurrent;

[RequireComponent(typeof(AudioListener))]
public class BCIAudioRenderer : MonoBehaviour
{
    [Header("SHM")]
    public string shmName = "Local_BCI_GustationRing";
    public int maxChannels = 8;
    public int pollIntervalMs = 4;

    [Header("Audio")]
    public float ringRadius = 3f;
    public float baseFrequency = 220f;
    public float volumeScale = 0.3f;
    public AnimationCurve intensityCurve = AnimationCurve.Linear(0, 0, 1, 1);

    // ── SHM P/Invoke (Windows) ──
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr OpenFileMapping(uint dwDesiredAccess, bool bInheritHandle, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr MapViewOfFile(IntPtr hFileMappingObject, uint dwDesiredAccess, uint dwFileOffsetHigh, uint dwFileOffsetLow, UIntPtr dwNumberOfBytesToMap);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UnmapViewOfFile(IntPtr lpBaseAddress);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);
    private const uint FILE_MAP_ALL_ACCESS = 0xF001F;
#endif

    private const int RingSize = 32;
    private const int HeaderSize = 24;
    private IntPtr _hMap = IntPtr.Zero, _shmBase = IntPtr.Zero;
    private bool _running;
    private long _lastHeartbeat;

    private struct FrameData { public float[] intensities; }
    private readonly ConcurrentQueue<FrameData> _inbox = new ConcurrentQueue<FrameData>();

    private AudioSource[] _sources;
    private float[] _targetVolumes;
    private float[] _frequencies;

    void Start()
    {
        BuildAudio();
        TryAttach();
    }

    void BuildAudio()
    {
        _sources = new AudioSource[maxChannels];
        _targetVolumes = new float[maxChannels];
        _frequencies = new float[maxChannels];

        float[] freqMultipliers = { 1f, 1.25f, 1.5f, 2f, 2.5f, 3f, 4f, 5f };

        for (int i = 0; i < maxChannels; i++)
        {
            _frequencies[i] = baseFrequency * freqMultipliers[i];

            var go = new GameObject("AudioCh" + i);
            go.transform.SetParent(transform);

            float angle = (float)i / maxChannels * Mathf.PI * 2f;
            go.transform.localPosition = new Vector3(
                Mathf.Cos(angle) * ringRadius,
                Mathf.Sin(angle * 2f) * 0.5f,
                Mathf.Sin(angle) * ringRadius
            );

            var src = go.AddComponent<AudioSource>();
            src.spatialBlend = 1f;
            src.minDistance = 0.5f;
            src.maxDistance = ringRadius * 2f;
            src.rolloffMode = AudioRolloffMode.Linear;
            src.loop = true;
            src.volume = 0f;
            src.clip = GenerateTone(_frequencies[i], 1f);
            src.Play();

            _sources[i] = src;
        }
    }

    AudioClip GenerateTone(float freq, float duration)
    {
        int sampleRate = AudioSettings.outputSampleRate;
        int samples = Mathf.RoundToInt(sampleRate * duration);
        var data = new float[samples];
        for (int i = 0; i < samples; i++)
        {
            float t = (float)i / sampleRate;
            data[i] = Mathf.Sin(2 * Mathf.PI * freq * t) * 0.5f
                    + Mathf.Sin(2 * Mathf.PI * freq * 2f * t) * 0.15f;
        }
        var clip = AudioClip.Create("Tone" + freq, samples, 1, sampleRate, false);
        clip.SetData(data, 0);
        return clip;
    }

    void TryAttach()
    {
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
        _hMap = OpenFileMapping(FILE_MAP_ALL_ACCESS, false, shmName);
        if (_hMap == IntPtr.Zero) return;
        _shmBase = MapViewOfFile(_hMap, FILE_MAP_ALL_ACCESS, 0, 0, UIntPtr.Zero);
        if (_shmBase == IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; return; }
        _running = true;
        new Thread(BackgroundWorker) { IsBackground = true }.Start();
#else
        Debug.LogWarning("[AUDIO] SHM only supported on Windows");
#endif
    }

    void BackgroundWorker()
    {
        int headOff = 8, tailOff = 16, chHeader = 8, chStride = 16;
        int slotStride = chHeader + maxChannels * chStride;

        while (_running)
        {
            long hb = Marshal.ReadInt64(_shmBase, 0);
            if (hb == _lastHeartbeat) { Thread.Sleep(pollIntervalMs); continue; }
            _lastHeartbeat = hb;
            long head = Marshal.ReadInt64(_shmBase, headOff);
            long tail = Marshal.ReadInt64(_shmBase, tailOff);

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
                _inbox.Enqueue(new FrameData { intensities = intensities });
                tail++;
                Marshal.WriteInt64(_shmBase, tailOff, tail);
            }
        }
    }

    void Update()
    {
        if (!_running) TryAttach();

        while (_inbox.TryDequeue(out FrameData frame))
        {
            for (int i = 0; i < frame.intensities.Length && i < _sources.Length; i++)
            {
                _targetVolumes[i] = intensityCurve.Evaluate(frame.intensities[i]) * volumeScale;
            }
        }

        for (int i = 0; i < _sources.Length; i++)
        {
            if (_sources[i] != null)
                _sources[i].volume = Mathf.Lerp(_sources[i].volume, _targetVolumes[i], 0.1f);
        }
    }

    void OnDestroy()
    {
        _running = false;
        if (_shmBase != IntPtr.Zero) { UnmapViewOfFile(_shmBase); _shmBase = IntPtr.Zero; }
        if (_hMap != IntPtr.Zero) { CloseHandle(_hMap); _hMap = IntPtr.Zero; }
    }
}
