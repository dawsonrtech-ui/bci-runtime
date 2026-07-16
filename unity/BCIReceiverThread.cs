using System;
using System.Threading;
using UnityEngine;
using NetMQ;
using NetMQ.Sockets;

[Serializable]
public class BCIPacket
{
    public int sample_id;
    public string engine_state;
    public float[] tangent_vector;
    public int predicted_action;
    public float confidence;
}

public class BCIReceiverThread : MonoBehaviour
{
    private Thread _receiveThread;
    private bool _isRunning;

    [Header("Network Settings")]
    public string connectionAddress = "tcp://127.0.0.1:5555";

    private readonly object _lock = new object();
    private BCIPacket _latestPacket = new BCIPacket();
    private bool _hasNewData;

    [Header("Runtime State")]
    public int lastAction;
    public float lastConfidence;
    public string lastState;

    private void Start()
    {
        _isRunning = true;
        _receiveThread = new Thread(ListenerLoop);
        _receiveThread.Start();
        Debug.Log("[BCI] Receiver thread started");
    }

    private void ListenerLoop()
    {
        AsyncIO.ForceDotNet.Force();

        using (var subSocket = new SubscriberSocket())
        {
            subSocket.Options.ReceiveHighWatermark = 10;
            subSocket.Connect(connectionAddress);
            subSocket.Subscribe("");

            while (_isRunning)
            {
                string jsonMessage;
                if (subSocket.TryReceiveFrameString(out jsonMessage))
                {
                    try
                    {
                        BCIPacket parsed = JsonUtility.FromJson<BCIPacket>(jsonMessage);
                        lock (_lock)
                        {
                            _latestPacket = parsed;
                            _hasNewData = true;
                        }
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning($"[BCI] Parse error: {ex.Message}");
                    }
                }
                else
                {
                    Thread.Sleep(1);
                }
            }
        }
        NetMQConfig.Cleanup();
    }

    private void Update()
    {
        lock (_lock)
        {
            if (_hasNewData)
            {
                lastAction = _latestPacket.predicted_action;
                lastConfidence = _latestPacket.confidence;
                lastState = _latestPacket.engine_state;
                ExecuteGameAction(_latestPacket.predicted_action, _latestPacket.confidence);
                _hasNewData = false;
            }
        }
    }

    private void ExecuteGameAction(int actionId, float confidence)
    {
        if (confidence < 0.70f) return;

        switch (actionId)
        {
            case 0:
                break;
            case 1:
                Debug.Log($"[BCI] Move forward (conf: {confidence:P})");
                break;
            case 2:
                Debug.Log($"[BCI] Jump (conf: {confidence:P})");
                break;
            case 3:
                Debug.Log($"[BCI] Interact (conf: {confidence:P})");
                break;
            default:
                Debug.Log($"[BCI] Action {actionId} (conf: {confidence:P})");
                break;
        }
    }

    public BCIPacket ReadPacket()
    {
        lock (_lock)
        {
            _hasNewData = false;
            return _latestPacket;
        }
    }

    private void OnDestroy()
    {
        _isRunning = false;
        if (_receiveThread != null && _receiveThread.IsAlive)
        {
            _receiveThread.Join(500);
        }
        Debug.Log("[BCI] Receiver thread stopped");
    }
}
