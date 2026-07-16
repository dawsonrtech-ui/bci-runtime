using System;
using System.Runtime.InteropServices;
using UnityEngine;

public class BCINativeBridge : MonoBehaviour
{
    #if UNITY_IPHONE && !UNITY_EDITOR
        private const string LIB_NAME = "__Internal";
    #else
        private const string LIB_NAME = "bci_core";
    #endif

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr create_covariance_engine(int n, double alpha, double gamma);

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern void rank1_update_cholesky(IntPtr state, double[] x, double weightModifier);

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern void get_shrunk_covariance(IntPtr state, double[] outSigma);

    [DllImport(LIB_NAME, CallingConvention = CallingConvention.Cdecl)]
    private static extern void destroy_covariance_engine(IntPtr state);

    private IntPtr _nativeEngineHandle;
    private int _channels = 8;
    private double[] _sigmaBuffer;

    void Awake()
    {
        _nativeEngineHandle = create_covariance_engine(_channels, 0.01, 0.05);
        _sigmaBuffer = new double[_channels * _channels];
        Debug.Log("Native C++ BCI Runtime Engine allocated via P/Invoke.");
    }

    public double[] StepPipeline(double[] rawFrame, double weight)
    {
        rank1_update_cholesky(_nativeEngineHandle, rawFrame, weight);
        get_shrunk_covariance(_nativeEngineHandle, _sigmaBuffer);
        return _sigmaBuffer;
    }

    void OnDestroy()
    {
        if (_nativeEngineHandle != IntPtr.Zero)
        {
            destroy_covariance_engine(_nativeEngineHandle);
            _nativeEngineHandle = IntPtr.Zero;
            Debug.Log("Native C++ BCI allocations released.");
        }
    }
}
