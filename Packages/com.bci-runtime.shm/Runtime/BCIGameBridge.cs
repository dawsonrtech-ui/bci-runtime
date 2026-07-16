using UnityEngine;
using Unity.Collections;
using Unity.Jobs;
using System;
using System.Runtime.InteropServices;

public class BCIGameBridge : MonoBehaviour
{
    #if UNITY_IPHONE && !UNITY_EDITOR
        private const string LIB_NAME = "__Internal";
    #else
        private const string LIB_NAME = "bci_bridge";
    #endif

    [StructLayout(LayoutKind.Sequential)]
    public struct BciBridgeFrame
    {
        public int version;
        public int frame_count;
        public int n_tangent;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 136)]
        public double[] tangent;
        public int predicted_action;
        public double confidence;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)]
        public string engine_state;

        public double camera_pos_x, camera_pos_y, camera_pos_z, camera_fov;
        public int spatial_nodes;
        public double dsp_gain, dsp_pan, dsp_occlusion;
        public double collision_impulse, thermal_target_c;
        public double intensity;
        public uint bulb_address;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 5)]
        public double[] gustation;
        public int motor_gating_active, in_high_stimulus, force_zero;
    }

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern int bci_serialize_frame(
        ref BciBridgeFrame frame, byte[] outBuffer, int maxLen);

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr bci_bridge_version();

    [Header("BCI Bridge Settings")]
    public int maxAudioNodes = 64;
    public AudioSource spatialAudioSource;
    public string engineState = "NORMAL";

    // --- Persistent native containers (zero GC allocation) ---
    private NativeArray<RaycastCommand> _raycastCommands;
    private NativeArray<RaycastHit> _raycastResults;
    private BciBridgeFrame _frame;
    private byte[] _jsonBuffer;
    private GCHandle _jsonHandle;
    private IntPtr _jsonPin;
    private int _frameCount;

    void Awake()
    {
        _raycastCommands = new NativeArray<RaycastCommand>(maxAudioNodes, Allocator.Persistent);
        _raycastResults = new NativeArray<RaycastHit>(maxAudioNodes, Allocator.Persistent);

        _frame = new BciBridgeFrame
        {
            version = 3,
            tangent = new double[136],
            gustation = new double[5],
            engine_state = engineState,
            spatial_nodes = maxAudioNodes,
            dsp_gain = 1.0f,
            thermal_target_c = 22.0f,
            motor_gating_active = 1,
        };

        _jsonBuffer = new byte[5120];
        _jsonHandle = GCHandle.Alloc(_jsonBuffer, GCHandleType.Pinned);
        _jsonPin = _jsonHandle.AddrOfPinnedObject();

        Debug.Log("BCIGameBridge initialized, lib: " +
                  Marshal.PtrToStringAnsi(bci_bridge_version()));
    }

    void Update()
    {
        _frameCount++;
        PackCameraRig();
        ScheduleOcclusionRaycasts();
        SerializeAndSend();
    }

    private void PackCameraRig()
    {
        Transform cam = Camera.main.transform;
        _frame.camera_pos_x = cam.position.x;
        _frame.camera_pos_y = cam.position.y;
        _frame.camera_pos_z = cam.position.z;
        _frame.camera_fov = Camera.main.fieldOfView;
    }

    private void ScheduleOcclusionRaycasts()
    {
        if (spatialAudioSource == null) return;

        int activeCount = Mathf.Min(maxAudioNodes, 1);
        Vector3 srcPos = spatialAudioSource.transform.position;
        Transform cam = Camera.main.transform;

        for (int i = 0; i < activeCount; i++)
        {
            Vector3 dir = srcPos - cam.position;
            float dist = dir.magnitude;
            _raycastCommands[i] = new RaycastCommand(
                cam.position,
                dir / dist,
                new QueryParameters(~0, false, QueryTriggerInteraction.Ignore, false),
                dist
            );
        }

        JobHandle job = RaycastCommand.ScheduleBatch(
            _raycastCommands, _raycastResults, 1, default);
        job.Complete();

        bool occluded = _raycastResults[0].collider != null;
        float hitDist = _raycastResults[0].distance;
        float srcDist = (srcPos - cam.position).magnitude;
        _frame.dsp_occlusion = occluded
            ? Mathf.Clamp01(hitDist / srcDist)
            : 0f;
        _frame.dsp_gain = occluded ? 0.3f : 1.0f;
    }

    void OnCollisionEnter(Collision collision)
    {
        _frame.collision_impulse = collision.impulse.magnitude;
    }

    void OnCollisionStay(Collision collision)
    {
        _frame.collision_impulse = Mathf.Max(
            _frame.collision_impulse, collision.impulse.magnitude);
    }

    void OnCollisionExit()
    {
        _frame.collision_impulse *= 0.5f;
    }

    void OnTriggerStay(Collider other)
    {
        ThermalZone tz = other.GetComponent<ThermalZone>();
        if (tz != null) _frame.thermal_target_c = tz.temperatureCelsius;

        OlfactoryZone oz = other.GetComponent<OlfactoryZone>();
        if (oz != null)
        {
            _frame.intensity = oz.intensity;
            _frame.bulb_address = oz.bulbAddress;
        }

        GustationZone gz = other.GetComponent<GustationZone>();
        if (gz != null)
        {
            _frame.gustation[0] = gz.sweet;
            _frame.gustation[1] = gz.salty;
            _frame.gustation[2] = gz.sour;
            _frame.gustation[3] = gz.bitter;
            _frame.gustation[4] = gz.umami;
        }
    }

    private void SerializeAndSend()
    {
        _frame.frame_count = _frameCount;
        _frame.engine_state = engineState;
        _frame.spatial_nodes = maxAudioNodes;

        int written = bci_serialize_frame(
            ref _frame, _jsonBuffer, _jsonBuffer.Length);

        if (written > 0)
        {
            string json = System.Text.Encoding.UTF8.GetString(
                _jsonBuffer, 0, written);
            SendToBCIPipeline(json);
        }
    }

    private void SendToBCIPipeline(string jsonFrame)
    {
        #if !UNITY_EDITOR
        var socket = BCIZmqSocket.Instance;
        if (socket != null) socket.Send(jsonFrame);
        #endif
    }

    public void SetEngineState(string state)
    {
        engineState = state;
        _frame.engine_state = state;
    }

    public void SetMotorGate(bool active, bool highStimulus)
    {
        _frame.motor_gating_active = active ? 1 : 0;
        _frame.in_high_stimulus = highStimulus ? 1 : 0;
    }

    void OnDestroy()
    {
        if (_raycastCommands.IsCreated) _raycastCommands.Dispose();
        if (_raycastResults.IsCreated) _raycastResults.Dispose();
        if (_jsonHandle.IsAllocated) _jsonHandle.Free();
    }
}

public class ThermalZone : MonoBehaviour
{
    public float temperatureCelsius = 22f;
}

public class OlfactoryZone : MonoBehaviour
{
    public float intensity = 0.5f;
    public uint bulbAddress = 0;
}

public class GustationZone : MonoBehaviour
{
    public float sweet = 0f;
    public float salty = 0f;
    public float sour = 0f;
    public float bitter = 0f;
    public float umami = 0f;
}
