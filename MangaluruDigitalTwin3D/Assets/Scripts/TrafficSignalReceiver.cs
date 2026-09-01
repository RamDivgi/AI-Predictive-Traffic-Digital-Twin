using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

[System.Serializable]
public class SignalData
{
    public string id;
    public string state;
}

[System.Serializable]

public class SignalPayload
{
    public SignalData[] signals;
}

public class TrafficSignalReceiver : MonoBehaviour
{
    public int listenPort = 5007;

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private SignalPayload latestPayload;
    private object dataLock = new object();
    
    private int packetsReceived = 0;
    private float lastLogTime = 0f;

    private Material matRedActive, matRedDim;
    private Material matYellowActive, matYellowDim;
    private Material matGreenActive, matGreenDim;

    private Dictionary<string, Renderer[]> signalRenderers = new Dictionary<string, Renderer[]>();
    private Dictionary<string, string> signalStateCache = new Dictionary<string, string>(); // NEW: State cache

    void Start()
    {
        // Use Unlit/Color which works across all pipelines as a safe fallback
        Shader unlitShader = Shader.Find("Unlit/Color");
        if (unlitShader == null) unlitShader = Shader.Find("Universal Render Pipeline/Unlit");

        Shader litShader = Shader.Find("Standard");
        if (litShader == null) litShader = Shader.Find("Universal Render Pipeline/Lit");

        matRedActive = new Material(unlitShader) { color = Color.red };
        matRedDim = new Material(litShader) { color = new Color(0.1f, 0, 0) };

        matYellowActive = new Material(unlitShader) { color = Color.yellow };
        matYellowDim = new Material(litShader) { color = new Color(0.1f, 0.1f, 0) };

        matGreenActive = new Material(unlitShader) { color = Color.green };
        matGreenDim = new Material(litShader) { color = new Color(0, 0.1f, 0) };

        StartUDPReceiver();
    }

    private void StartUDPReceiver()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("TrafficSignalReceiver: Started UDP listener on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            udpClient.Client.ReceiveBufferSize = 65535;

            while (isRunning)
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);

                try
                {
                    SignalPayload payload = JsonUtility.FromJson<SignalPayload>(text);

                    if (payload != null && payload.signals != null)
                    {
                        lock (dataLock)
                        {
                            latestPayload = payload;
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning("Failed to parse TLS JSON: " + e.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning)
            {
                Debug.LogError("UDP receive thread error (TLS): " + err.ToString());
            }
        }
    }

    void Update()
    {
        SignalPayload payload = null;

        lock (dataLock)
        {
            if (latestPayload != null)
            {
                payload = latestPayload;
                latestPayload = null; 
            }
        }

        if (payload != null && payload.signals != null)
        {
            int updatedSignals = 0;
            foreach (SignalData sig in payload.signals)
            {
                // Cache check: Skip material assignment if state hasn't changed
                if (signalStateCache.TryGetValue(sig.id, out string cachedState))
                {
                    if (cachedState == sig.state)
                    {
                        continue;
                    }
                }

                Renderer[] rends;
                if (!signalRenderers.TryGetValue(sig.id, out rends))
                {
                    GameObject tlsObj = GameObject.Find("TLS_" + sig.id);
                    if (tlsObj != null)
                    {
                        Transform head = tlsObj.transform.Find("Head");
                        if (head != null)
                        {
                            Transform rLight = head.Find("Light_R");
                            Transform yLight = head.Find("Light_Y");
                            Transform gLight = head.Find("Light_G");
                            if (rLight != null && yLight != null && gLight != null)
                            {
                                rends = new Renderer[] {
                                    rLight.GetComponent<Renderer>(),
                                    yLight.GetComponent<Renderer>(),
                                    gLight.GetComponent<Renderer>()
                                };
                                signalRenderers[sig.id] = rends;
                            }
                        }
                    }
                }

                if (rends != null)
                {
                    string stateLower = sig.state.ToLower();
                    bool isGreen = stateLower.Contains("g");
                    bool isYellow = !isGreen && stateLower.Contains("y");
                    bool isRed = !isGreen && !isYellow && stateLower.Contains("r");

                    rends[0].sharedMaterial = isRed ? matRedActive : matRedDim;
                    rends[1].sharedMaterial = isYellow ? matYellowActive : matYellowDim;
                    rends[2].sharedMaterial = isGreen ? matGreenActive : matGreenDim;
                    
                    // Update cache
                    signalStateCache[sig.id] = sig.state;
                    updatedSignals++;
                }
            }
            
            packetsReceived++;
            if (Time.time - lastLogTime >= 15.0f && updatedSignals > 0)
            {
                Debug.Log($"TrafficSignalReceiver: Active signals = {payload.signals.Length} | Visual materials applied for {updatedSignals} changed signals.");
                lastLogTime = Time.time;
            }
        }
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Abort();
        }
        if (udpClient != null)
        {
            udpClient.Close();
        }
    }
}
