using UnityEngine;
using UnityEngine.UI;
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

public class BCIDashboard : MonoBehaviour
{
    [Header("SHM Config")]
    public int maxChannels = 8;

    [Header("Display Config")]
    public Color baseColor = new Color(0.15f, 0.15f, 0.15f);
    public Color hotColor = new Color(1f, 0.3f, 0f);
    public float influenceRadius = 0.3f;
    public bool recordingEnabled = false;
    public string recordPath = "recordings";

    private ShmAutoReconnector _shm;
    private ShmReturnWriter _returnWriter;

    private long _ackCount, _frameCount;
    private float _fpsAccum;
    private int _fpsFrames;

    // Topography
    private BCITopographyMeshDriver _driver;
    private Transform[] _electrodes;

    // Waveform
    private class ChannelWaveform { public float[] buffer; public int head; public Color[] pix; }
    private ChannelWaveform[] _waveforms;
    private RawImage[] _waveformImages;
    private Texture2D[] _waveformTex;

    // Control panel
    private Text _fpsLabel, _ackLabel, _statusLabel, _chLabels;
    private Button[] _cmdButtons;

    // Recording
    private StreamWriter _recWriter;
    private float _recStartTime;
    private int _recFrameCount;

    void Start()
    {
        _shm = gameObject.AddComponent<ShmAutoReconnector>();
        _shm.OnFrame += OnFrameData;
        _shm.OnConnected += () => { if (_statusLabel != null) _statusLabel.text = "Connected"; };
        _shm.OnDisconnected += () => { if (_statusLabel != null) _statusLabel.text = "Disconnected — reconnecting..."; };

        _returnWriter = new ShmReturnWriter();
        _returnWriter.Connect();

        BuildDashboard();
    }

    void OnDestroy()
    {
        ToggleRecording(false);
        if (_returnWriter != null) { _returnWriter.Dispose(); _returnWriter = null; }
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Escape)) { ToggleRecording(false); Application.Quit(); }

        _fpsFrames++;
        _fpsAccum += Time.unscaledDeltaTime;
        if (Time.unscaledTime >= Mathf.Floor(Time.unscaledTime) + 1f && _fpsLabel != null)
        {
            _fpsLabel.text = $"FPS: {Mathf.RoundToInt(_fpsFrames / _fpsAccum)}";
            _fpsFrames = 0;
            _fpsAccum = 0;
        }

        if (_ackLabel != null) _ackLabel.text = $"ACKs: {_ackCount}";
    }

    void OnFrameData(float[] intensities)
    {
        _frameCount++;
        if (_driver != null) _driver.UpdateScalpPotentials(intensities);
        UpdateWaveform(intensities);

        if (_returnWriter != null)
        {
            _returnWriter.SendAck((ulong)_frameCount, Time.realtimeSinceStartup);
            _ackCount++;
        }

        if (_chLabels != null)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < intensities.Length && i < maxChannels; i++)
                sb.AppendLine($"Ch{i}: {intensities[i]:F3}");
            _chLabels.text = sb.ToString();
        }

        if (recordingEnabled) RecordFrame(intensities);
    }

    // ═══════════════════════ UI BUILD ═══════════════════════

    void BuildDashboard()
    {
        BuildScalpMesh();
        BuildWaveform();
        BuildControlPanel();
    }

    // ═══════════ SCALP TOPOGRAPHY ═══════════

    void BuildScalpMesh()
    {
        int segments = 32, rings = 12;
        float radius = 1f;

        var mesh = new Mesh();
        var verts = new List<Vector3>();
        var tris = new List<int>();
        var uvs = new List<Vector2>();

        verts.Add(new Vector3(0, radius * 0.3f, 0));
        uvs.Add(new Vector2(0.5f, 0.5f));

        for (int r = 1; r <= rings; r++)
        {
            float lat = (float)r / rings * Mathf.PI * 0.5f;
            float y = Mathf.Cos(lat) * radius;
            float rr = Mathf.Sin(lat) * radius;
            for (int s = 0; s < segments; s++)
            {
                float lon = (float)s / segments * Mathf.PI * 2f;
                verts.Add(new Vector3(Mathf.Cos(lon) * rr, y, Mathf.Sin(lon) * rr));
                uvs.Add(new Vector2((float)s / segments, (float)r / rings));
                int v = verts.Count - 1;
                if (r == 1) { tris.Add(0); tris.Add(v); tris.Add((s + 1) % segments + 1); }
                else
                {
                    int pr = (r - 2) * segments + 1, cr = (r - 1) * segments + 1, nx = (s + 1) % segments;
                    tris.Add(pr + s); tris.Add(cr + s); tris.Add(pr + nx);
                    tris.Add(cr + s); tris.Add(cr + nx); tris.Add(pr + nx);
                }
            }
        }

        mesh.SetVertices(verts);
        mesh.SetIndices(tris.ToArray(), MeshTopology.Triangles, 0);
        mesh.SetUVs(0, uvs);
        mesh.RecalculateNormals();

        var mf = gameObject.AddComponent<MeshFilter>();
        mf.sharedMesh = mesh;

        var mat = new Material(Shader.Find("BCI/ScalpTopography"));
        mat.SetColor("_BaseColor", baseColor);
        mat.SetColor("_HotColor", hotColor);
        mat.SetFloat("_InfluenceRadius", influenceRadius);

        var mr = gameObject.AddComponent<MeshRenderer>();
        mr.sharedMaterial = mat;

        _electrodes = new Transform[maxChannels];
        string[] labels = { "Fz","C3","Cz","C4","Pz","O1","O2","T3","T4","F3","F4","P3","P4","F7","F8","T5" };
        for (int i = 0; i < maxChannels; i++)
        {
            float angle = (float)i / maxChannels * Mathf.PI * 2f;
            float latAngle = Mathf.PI * 0.35f;
            float x = Mathf.Cos(angle) * Mathf.Sin(latAngle) * radius;
            float y = Mathf.Cos(latAngle) * radius;
            float z = Mathf.Sin(angle) * Mathf.Sin(latAngle) * radius;
            var e = new GameObject("Electrode" + i);
            e.transform.SetParent(transform);
            e.transform.localPosition = new Vector3(x, y, z);
            _electrodes[i] = e.transform;
            var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sphere.transform.SetParent(e.transform);
            sphere.transform.localPosition = Vector3.zero;
            sphere.transform.localScale = Vector3.one * 0.05f;
            Destroy(sphere.GetComponent<Collider>());
            sphere.GetComponent<MeshRenderer>().material.color = Color.white;
        }

        _driver = gameObject.AddComponent<BCITopographyMeshDriver>();
        _driver.electrodeTransforms = _electrodes;

        Camera cam = Camera.main;
        if (cam != null)
        {
            cam.transform.position = new Vector3(-2.8f, 2.2f, 0f);
            cam.transform.LookAt(new Vector3(0, 0.3f, 0));
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.06f, 0.06f, 0.06f);
        }

        var dl = new GameObject("DirectionalLight");
        dl.transform.position = new Vector3(5, 10, 5);
        dl.transform.LookAt(Vector3.zero);
        var light = dl.AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 0.8f;
    }

    // ═══════════ WAVEFORM ═══════════

    void BuildWaveform()
    {
        int bufLen = 256;
        _waveforms = new ChannelWaveform[maxChannels];
        _waveformImages = new RawImage[maxChannels];
        _waveformTex = new Texture2D[maxChannels];

        var uiRoot = EnsureCanvas("UIWaveform", 0);
        var panel = new GameObject("WaveformPanel");
        panel.transform.SetParent(uiRoot, false);
        var pRT = panel.AddComponent<RectTransform>();
        pRT.anchorMin = new Vector2(0, 0);
        pRT.anchorMax = new Vector2(0.18f, 1);
        pRT.offsetMin = new Vector2(8, 8);
        pRT.offsetMax = new Vector2(-8, -8);

        var bg = panel.AddComponent<Image>();
        bg.color = new Color(0, 0, 0, 0.55f);

        float chH = 22f;

        for (int i = 0; i < maxChannels; i++)
        {
            _waveforms[i] = new ChannelWaveform { buffer = new float[bufLen], head = 0, pix = new Color[bufLen] };
            _waveformTex[i] = new Texture2D(bufLen, 1, TextureFormat.RFloat, false);
            _waveformTex[i].filterMode = FilterMode.Point;
            _waveformTex[i].wrapMode = TextureWrapMode.Clamp;
            var pix = new Color[bufLen];
            for (int p = 0; p < bufLen; p++) pix[p] = Color.black;
            _waveformTex[i].SetPixels(pix);
            _waveformTex[i].Apply();

            var imgGO = new GameObject("Wav" + i);
            imgGO.transform.SetParent(panel.transform, false);
            var img = imgGO.AddComponent<RawImage>();
            img.texture = _waveformTex[i];
            img.color = Color.Lerp(Color.blue, Color.red, (float)i / maxChannels);
            var rt = imgGO.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(1, 1);
            rt.offsetMin = new Vector2(4, -(i + 1) * chH - 2);
            rt.offsetMax = new Vector2(-4, -i * chH - 2);
            _waveformImages[i] = img;
        }
    }

    void UpdateWaveform(float[] intensities)
    {
        for (int i = 0; i < intensities.Length && i < maxChannels; i++)
        {
            var w = _waveforms[i];
            if (w == null) continue;
            w.buffer[w.head] = intensities[i];
            w.head = (w.head + 1) % w.buffer.Length;
        }
        for (int i = 0; i < maxChannels; i++)
        {
            if (_waveformTex[i] == null) continue;
            var w = _waveforms[i];
            int bufLen = w.buffer.Length;
            for (int p = 0; p < bufLen; p++)
            {
                int idx = (w.head + p) % bufLen;
                float val = Mathf.Clamp01(w.buffer[idx]);
                w.pix[p].r = val; w.pix[p].g = val; w.pix[p].b = val; w.pix[p].a = 1f;
            }
            _waveformTex[i].SetPixels(w.pix);
            _waveformTex[i].Apply();
        }
    }

    // ═══════════ CONTROL PANEL ═══════════

    Transform EnsureCanvas(string name, int sortOrder)
    {
        var go = GameObject.Find(name);
        if (go != null) return go.transform;
        go = new GameObject(name);
        var c = go.AddComponent<Canvas>();
        c.renderMode = RenderMode.ScreenSpaceOverlay;
        c.sortingOrder = sortOrder;
        go.AddComponent<CanvasScaler>();
        go.AddComponent<GraphicRaycaster>();
        return go.transform;
    }

    void BuildControlPanel()
    {
        var uiRoot = EnsureCanvas("UIControls", 1);

        var panel = new GameObject("ControlPanel");
        panel.transform.SetParent(uiRoot, false);
        var pRT = panel.AddComponent<RectTransform>();
        pRT.anchorMin = new Vector2(0.82f, 0);
        pRT.anchorMax = new Vector2(1, 1);
        pRT.offsetMin = new Vector2(8, 8);
        pRT.offsetMax = new Vector2(-8, -8);

        var bg = panel.AddComponent<Image>();
        bg.color = new Color(0, 0, 0, 0.55f);

        float px = 10, py = -10;

        _fpsLabel = MakeLabel(panel.transform, "FPSLabel", "FPS: --", 18, TextAnchor.MiddleLeft, new Vector2(px, py));
        py -= 26;
        _ackLabel = MakeLabel(panel.transform, "AckLabel", "ACKs: 0", 18, TextAnchor.MiddleLeft, new Vector2(px, py));
        py -= 26;
        _statusLabel = MakeLabel(panel.transform, "StatusLabel", "Connecting...", 18, TextAnchor.MiddleLeft, new Vector2(px, py));
        py -= 30;
        _chLabels = MakeLabel(panel.transform, "ChLabels", "", 13, TextAnchor.UpperLeft, new Vector2(px, py));
        py -= 180;
        py -= 10;

        string[] cmds = { "5 Hz", "10 Hz", "20 Hz", "50 Hz", "100 Hz", "Reset", "Stop" };
        _cmdButtons = new Button[cmds.Length];
        for (int i = 0; i < cmds.Length; i++)
        {
            var btnGO = new GameObject("Cmd" + cmds[i]);
            btnGO.transform.SetParent(panel.transform, false);
            var btn = btnGO.AddComponent<Button>();
            var colors = btn.colors;
            colors.normalColor = new Color(0.2f, 0.2f, 0.2f);
            colors.highlightedColor = new Color(0.35f, 0.35f, 0.35f);
            btn.colors = colors;

            var img = btnGO.AddComponent<Image>();
            img.color = new Color(0.2f, 0.2f, 0.2f);

            var txtGO = new GameObject("Text");
            txtGO.transform.SetParent(btnGO.transform, false);
            var txt = txtGO.AddComponent<Text>();
            txt.text = cmds[i];
            txt.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            txt.fontSize = 13;
            txt.alignment = TextAnchor.MiddleCenter;
            txt.color = Color.white;
            var trt = txtGO.GetComponent<RectTransform>();
            trt.anchorMin = Vector2.zero;
            trt.anchorMax = Vector2.one;
            trt.sizeDelta = Vector2.zero;

            var rt = btnGO.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(0, 1);
            rt.sizeDelta = new Vector2(70, 26);
            int col = i % 2, row = i / 2;
            rt.anchoredPosition = new Vector3(px + col * 78, py - row * 30, 0);

            int freq = cmds[i] == "5 Hz" ? 5 : cmds[i] == "10 Hz" ? 10
                    : cmds[i] == "20 Hz" ? 20 : cmds[i] == "50 Hz" ? 50
                    : cmds[i] == "100 Hz" ? 100 : cmds[i] == "Reset" ? -1 : -2;
            int f = freq;
            btn.onClick.AddListener(() => SendCommand(f));
            _cmdButtons[i] = btn;
        }

        int btnRows = (cmds.Length + 1) / 2;
        float buttonsBottom = py - btnRows * 30 - 10;

        var togGO = new GameObject("RecToggle");
        togGO.transform.SetParent(panel.transform, false);
        var tog = togGO.AddComponent<Toggle>();
        var togImg = togGO.AddComponent<Image>();
        togImg.color = new Color(0.3f, 0.1f, 0.1f);
        var togRt = togGO.GetComponent<RectTransform>();
        togRt.anchorMin = new Vector2(0, 1);
        togRt.anchorMax = new Vector2(0, 1);
        togRt.sizeDelta = new Vector2(20, 20);
        togRt.anchoredPosition = new Vector3(px, buttonsBottom, 0);

        var togLabelObj = new GameObject("RecLabel");
        togLabelObj.transform.SetParent(panel.transform, false);
        var togLbl = togLabelObj.AddComponent<Text>();
        togLbl.text = "Record";
        togLbl.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        togLbl.fontSize = 15;
        togLbl.alignment = TextAnchor.MiddleLeft;
        togLbl.color = Color.white;
        var tlRT = togLabelObj.GetComponent<RectTransform>();
        tlRT.anchorMin = new Vector2(0, 1);
        tlRT.anchorMax = new Vector2(0, 1);
        tlRT.sizeDelta = new Vector2(100, 24);
        tlRT.anchoredPosition = new Vector3(px + 26, buttonsBottom, 0);

        tog.onValueChanged.AddListener(v => { recordingEnabled = v; ToggleRecording(v); });
    }

    Text MakeLabel(Transform parent, string name, string text, int fontSize,
        TextAnchor align, Vector2 anchoredPos)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var lbl = go.AddComponent<Text>();
        lbl.text = text;
        lbl.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        lbl.fontSize = fontSize;
        lbl.alignment = align;
        lbl.color = Color.white;
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(0, 1);
        rt.anchorMax = new Vector2(0, 1);
        rt.sizeDelta = new Vector2(240, 22);
        rt.anchoredPosition = anchoredPos;
        return lbl;
    }

    void SendCommand(int freq)
    {
        string cmd = "";
        if (freq > 0) cmd = $"SET_FREQ {freq}";
        else if (freq == -1) cmd = "RESET";
        else if (freq == -2) cmd = "STOP";
        if (_returnWriter != null && !string.IsNullOrEmpty(cmd))
        {
            _returnWriter.SendCommand(cmd);
            Debug.Log("[CMD] Sent: " + cmd);
        }
    }

    void ToggleRecording(bool on)
    {
        if (on && _recWriter == null)
        {
            try
            {
                if (!Directory.Exists(recordPath)) Directory.CreateDirectory(recordPath);
                string path = Path.Combine(recordPath, $"bci_rec_{DateTime.Now:yyyyMMdd_HHmmss}.csv");
                _recWriter = new StreamWriter(path, false, Encoding.UTF8);
                _recWriter.WriteLine("frame_n,channel,value");
                _recStartTime = Time.time;
                _recFrameCount = 0;
                Debug.Log("[REC] Started: " + path);
            }
            catch (Exception e) { Debug.LogError("[REC] " + e.Message); }
        }
        else if (!on && _recWriter != null)
        {
            _recWriter.Close();
            _recWriter = null;
            int elapsed = Mathf.RoundToInt(Time.time - _recStartTime);
            Debug.Log($"[REC] Done: {_recFrameCount} frames in {elapsed}s");
        }
    }

    void RecordFrame(float[] intensities)
    {
        if (_recWriter == null) return;
        _recFrameCount++;
        for (int i = 0; i < intensities.Length && i < maxChannels; i++)
            _recWriter.WriteLine($"{_recFrameCount},{i},{intensities[i]:F6}");
    }
}
