using System;
using System.Collections.Generic;
using System.IO;
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
    private Dictionary<string, string> signalStateCache = new Dictionary<string, string>();

    // Mapping: tlsID -> fromEdge -> list of link indices
    private Dictionary<string, Dictionary<string, List<int>>> tlsEdgeToLinks = new Dictionary<string, Dictionary<string, List<int>>>();

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

        LoadRoadNetwork();
        StartUDPReceiver();
    }

    private void LoadRoadNetwork()
    {
        string filePath = Path.Combine(Application.dataPath, "Generated", "RoadNetwork.json");
        if (!File.Exists(filePath))
        {
            Debug.LogError("TrafficSignalReceiver: RoadNetwork.json not found!");
            return;
        }

        string jsonContent = File.ReadAllText(filePath);
        RoadNetworkData networkData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);

        if (networkData != null && networkData.traffic_lights != null)
        {
            foreach (TlsData tls in networkData.traffic_lights)
            {
                if (!tlsEdgeToLinks.ContainsKey(tls.id))
                    tlsEdgeToLinks[tls.id] = new Dictionary<string, List<int>>();

                if (tls.controlled_links != null)
                {
                    foreach (TlsLinkData link in tls.controlled_links)
                    {
                        if (string.IsNullOrEmpty(link.from_lane) || link.from_lane.StartsWith(":"))
                            continue;

                        int lastUnderscore = link.from_lane.LastIndexOf('_');
                        string fromEdge = lastUnderscore > 0 ? link.from_lane.Substring(0, lastUnderscore) : link.from_lane;

                        if (!tlsEdgeToLinks[tls.id].ContainsKey(fromEdge))
                            tlsEdgeToLinks[tls.id][fromEdge] = new List<int>();

                        tlsEdgeToLinks[tls.id][fromEdge].Add(link.link_index);
                    }
                }
            }
        }
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
                // Skip if we don't have mapping for this TLS
                if (!tlsEdgeToLinks.ContainsKey(sig.id)) continue;
                
                // Cache check: Skip material assignment if the state string hasn't changed for this TLS
                if (signalStateCache.TryGetValue(sig.id, out string cachedState))
                {
                    if (cachedState == sig.state)
                    {
                        continue;
                    }
                }

                GameObject tlsObj = GameObject.Find("TLS_" + sig.id);
                if (tlsObj == null)
                {
                    GameObject parent = GameObject.Find("MangaluruDigitalTwin/Traffic/TrafficSignals")
                                     ?? GameObject.Find("Traffic/TrafficSignals")
                                     ?? GameObject.Find("TrafficSignals")
                                     ?? GameObject.Find("SUMO_TLS");
                    if (parent != null)
                    {
                        Transform t = parent.transform.Find("TLS_" + sig.id);
                        if (t != null) tlsObj = t.gameObject;
                    }
                }
                if (tlsObj == null) continue;

                bool allApproachesResolved = true;

                // Process each physical approach
                foreach (var kvp in tlsEdgeToLinks[sig.id])
                {
                    string fromEdge = kvp.Key;
                    List<int> linkIndices = kvp.Value;
                    
                    string cacheKey = sig.id + "_" + fromEdge;

                    Renderer[] rends;
                    if (!signalRenderers.TryGetValue(cacheKey, out rends))
                    {
                        Transform signalHead = tlsObj.transform.Find("Signal_" + fromEdge);
                        if (signalHead != null)
                        {
                            Transform rLight = signalHead.Find("red_light") ?? FindChildRecursive(signalHead, "red_light");
                            Transform yLight = signalHead.Find("yellow_light") ?? FindChildRecursive(signalHead, "yellow_light");
                            Transform gLight = signalHead.Find("green_light") ?? FindChildRecursive(signalHead, "green_light");

                            if (rLight != null && yLight != null && gLight != null)
                            {
                                Renderer rRend = rLight.GetComponentInChildren<Renderer>();
                                Renderer yRend = yLight.GetComponentInChildren<Renderer>();
                                Renderer gRend = gLight.GetComponentInChildren<Renderer>();

                                if (rRend != null && yRend != null && gRend != null)
                                {
                                    rends = new Renderer[] { rRend, yRend, gRend };
                                    signalRenderers[cacheKey] = rends;
                                }
                            }
                        }
                    }

                    if (rends != null)
                    {
                        bool isRed = false;
                        bool isYellow = false;
                        bool isGreen = false;

                        // Safest visualization: Prioritize Red > Yellow > Green 
                        // so we never show a false green to the ambulance if any of its approach lanes are red.
                        foreach (int idx in linkIndices)
                        {
                            if (idx >= 0 && idx < sig.state.Length)
                            {
                                char c = char.ToLower(sig.state[idx]);
                                if (c == 'r' || c == 's') isRed = true;
                                else if (c == 'y') isYellow = true;
                                else if (c == 'g') isGreen = true;
                            }
                        }

                        // Determine final material for this physical signal head
                        rends[0].sharedMaterial = isRed ? matRedActive : matRedDim;
                        rends[1].sharedMaterial = (!isRed && isYellow) ? matYellowActive : matYellowDim;
                        rends[2].sharedMaterial = (!isRed && !isYellow && isGreen) ? matGreenActive : matGreenDim;

                        updatedSignals++;
                    }
                    else
                    {
                        allApproachesResolved = false;
                    }
                }

                // Update cache only when all approaches for this TLS are resolved
                if (allApproachesResolved)
                {
                    signalStateCache[sig.id] = sig.state;
                }
            }
            
            packetsReceived++;
            if (Time.time - lastLogTime >= 15.0f && updatedSignals > 0)
            {
                Debug.Log($"TrafficSignalReceiver: Active signals = {payload.signals.Length} | Visual materials applied for {updatedSignals} changed approaches.");
                lastLogTime = Time.time;
            }
        }
    }

    private Transform FindChildRecursive(Transform parent, string childName)
    {
        for (int i = 0; i < parent.childCount; i++)
        {
            Transform child = parent.GetChild(i);
            if (child.name == childName) return child;
            Transform found = FindChildRecursive(child, childName);
            if (found != null) return found;
        }
        return null;
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
