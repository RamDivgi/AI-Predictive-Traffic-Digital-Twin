using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

[System.Serializable]
public class RoutePoint
{
    public float x;
    public float z;
}

[System.Serializable]
public class RoutePayload
{
    public string type;
    public int chunk_index;
    public int total_chunks;
    public RoutePoint[] points;
}

public class RouteReceiver : MonoBehaviour
{
    public int listenPort = 5008;
    public float yOffset = 0.12f; // Elevated cleanly above road surface (0.0m) and lane markings (0.05m)
    public float lineWidth = 0.50f; // Clear, conservative navigation path width (50 cm)
    public Color routeColor = new Color(0.15f, 0.72f, 1.0f, 1.0f); // Vibrant emergency navigation cyan

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private LineRenderer lineRenderer;
    private RoutePayload latestPayload;
    private object dataLock = new object();
    private bool hasNewData = false;
    
    // Chunking support
    private RoutePoint[][] chunksBuffer;
    private int chunksReceived = 0;
    private int currentTotalChunks = 0;

    // Destination Marker
    private GameObject destinationMarkerRoot;
    private Transform billboardTransform;
    private GameObject billboardBackplate;
    private TextMesh destinationTextMesh;
    private TextMesh destinationShadowMesh;
    private Transform beaconTransform;
    private HospitalData[] cachedHospitals;
    private Transform ambulanceTransform;
    private float lastRouteTime = 0f;

    void Start()
    {
        InitializeLineRenderer();
        LoadHospitalData();
        InitializeDestinationMarker();
        StartUDPReceiver();

        GameObject ambObj = GameObject.Find("Ambulance");
        if (ambObj != null) ambulanceTransform = ambObj.transform;
    }

    private void InitializeLineRenderer()
    {
        lineRenderer = gameObject.GetComponent<LineRenderer>();
        if (lineRenderer == null)
        {
            lineRenderer = gameObject.AddComponent<LineRenderer>();
        }

        lineRenderer.positionCount = 0;
        lineRenderer.startWidth = lineWidth;
        lineRenderer.endWidth = lineWidth;
        lineRenderer.useWorldSpace = false; // MUST be false to inherit MangaluruDigitalTwin offset
        
        // Attempt to find a suitable unlit shader so the line glows/stands out
        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");
        
        Material lineMat = new Material(unlitShader);
        lineMat.color = routeColor;
        lineRenderer.material = lineMat;
    }

    private void LoadHospitalData()
    {
        try
        {
            string filePath = System.IO.Path.Combine(Application.dataPath, "Generated", "RoadNetwork.json");
            if (System.IO.File.Exists(filePath))
            {
                string jsonContent = System.IO.File.ReadAllText(filePath);
                RoadNetworkData netData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);
                if (netData != null && netData.hospitals != null)
                {
                    cachedHospitals = netData.hospitals;
                }
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning("RouteReceiver: Could not pre-cache hospital data: " + ex.Message);
        }
    }

    private void InitializeDestinationMarker()
    {
        destinationMarkerRoot = new GameObject("RouteDestinationMarker");
        destinationMarkerRoot.transform.SetParent(transform, false);

        Shader litShader = Shader.Find("Universal Render Pipeline/Lit");
        if (litShader == null) litShader = Shader.Find("Standard");

        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");

        Material stemMat = new Material(unlitShader);
        stemMat.color = new Color(0.15f, 0.85f, 1.0f); // Bright cyan light stem

        Material beaconMat = new Material(unlitShader);
        beaconMat.color = new Color(1.0f, 0.85f, 0.20f); // Amber glowing beacon

        Material plateMat = new Material(litShader);
        Color plateCol = new Color(0.08f, 0.12f, 0.20f, 0.95f);
        plateMat.color = plateCol;
        if (plateMat.HasProperty("_BaseColor")) plateMat.SetColor("_BaseColor", plateCol);

        // 1. Vertical Pin Stem (12m tall, cylinder centered at Y = 6m)
        GameObject stem = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        stem.name = "Stem";
        stem.transform.SetParent(destinationMarkerRoot.transform, false);
        stem.transform.localPosition = new Vector3(0f, 6.0f, 0f);
        stem.transform.localRotation = Quaternion.identity;
        stem.transform.localScale = new Vector3(0.35f, 6.0f, 0.35f);
        Destroy(stem.GetComponent<Collider>());
        stem.GetComponent<Renderer>().material = stemMat;

        // 2. Pulsing Beacon Sphere (atop stem at Y = 12m)
        GameObject beacon = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        beacon.name = "Beacon";
        beacon.transform.SetParent(destinationMarkerRoot.transform, false);
        beacon.transform.localPosition = new Vector3(0f, 12.0f, 0f);
        beacon.transform.localRotation = Quaternion.identity;
        beacon.transform.localScale = new Vector3(1.6f, 1.6f, 1.6f);
        Destroy(beacon.GetComponent<Collider>());
        beacon.GetComponent<Renderer>().material = beaconMat;
        beaconTransform = beacon.transform;

        // 3. Floating Billboard at Y = 14.5m
        GameObject billboard = new GameObject("DestinationBillboard");
        billboard.transform.SetParent(destinationMarkerRoot.transform, false);
        billboard.transform.localPosition = new Vector3(0f, 14.5f, 0f);
        billboardTransform = billboard.transform;

        // Backplate
        billboardBackplate = GameObject.CreatePrimitive(PrimitiveType.Cube);
        billboardBackplate.name = "Backplate";
        billboardBackplate.transform.SetParent(billboard.transform, false);
        billboardBackplate.transform.localPosition = Vector3.zero;
        billboardBackplate.transform.localRotation = Quaternion.identity;
        billboardBackplate.transform.localScale = new Vector3(16.0f, 3.2f, 0.3f);
        Destroy(billboardBackplate.GetComponent<Collider>());
        billboardBackplate.GetComponent<Renderer>().material = plateMat;

        // Text
        GameObject labelObj = new GameObject("LabelText");
        labelObj.transform.SetParent(billboardBackplate.transform, false);
        labelObj.transform.localPosition = new Vector3(0f, 0f, -0.2f);
        labelObj.transform.localRotation = Quaternion.identity;

        destinationTextMesh = labelObj.AddComponent<TextMesh>();
        destinationTextMesh.characterSize = 0.22f;
        destinationTextMesh.fontSize = 64;
        destinationTextMesh.fontStyle = FontStyle.Bold;
        destinationTextMesh.anchor = TextAnchor.MiddleCenter;
        destinationTextMesh.alignment = TextAlignment.Center;
        destinationTextMesh.color = new Color(1.0f, 0.90f, 0.20f); // Bright Gold/Yellow

        // Shadow text for high-contrast readability
        GameObject shadowObj = new GameObject("ShadowText");
        shadowObj.transform.SetParent(billboardBackplate.transform, false);
        shadowObj.transform.localPosition = new Vector3(0.04f, -0.04f, -0.15f);
        shadowObj.transform.localRotation = Quaternion.identity;

        destinationShadowMesh = shadowObj.AddComponent<TextMesh>();
        destinationShadowMesh.characterSize = 0.22f;
        destinationShadowMesh.fontSize = 64;
        destinationShadowMesh.fontStyle = FontStyle.Bold;
        destinationShadowMesh.anchor = TextAnchor.MiddleCenter;
        destinationShadowMesh.alignment = TextAlignment.Center;
        destinationShadowMesh.color = Color.black;

        destinationMarkerRoot.SetActive(false);
    }

    private void StartUDPReceiver()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("RouteReceiver: Started UDP listener on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            while (isRunning)
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);

                try
                {
                    RoutePayload payload = JsonUtility.FromJson<RoutePayload>(text);
                    if (payload != null && (payload.type == "route" || payload.type == "route_chunk") && payload.points != null)
                    {
                        lock (dataLock)
                        {
                            if (payload.total_chunks <= 1 || payload.type == "route")
                            {
                                // Single payload
                                latestPayload = payload;
                                hasNewData = true;
                            }
                            else
                            {
                                // Handle chunks
                                if (chunksBuffer == null || currentTotalChunks != payload.total_chunks)
                                {
                                    chunksBuffer = new RoutePoint[payload.total_chunks][];
                                    chunksReceived = 0;
                                    currentTotalChunks = payload.total_chunks;
                                }

                                if (payload.chunk_index >= 0 && payload.chunk_index < payload.total_chunks)
                                {
                                    if (chunksBuffer[payload.chunk_index] == null)
                                    {
                                        chunksBuffer[payload.chunk_index] = payload.points;
                                        chunksReceived++;

                                        if (chunksReceived == currentTotalChunks)
                                        {
                                            // All chunks received, assemble them
                                            int totalPoints = 0;
                                            for (int i = 0; i < currentTotalChunks; i++)
                                            {
                                                totalPoints += chunksBuffer[i].Length;
                                            }

                                            RoutePoint[] allPoints = new RoutePoint[totalPoints];
                                            int offset = 0;
                                            for (int i = 0; i < currentTotalChunks; i++)
                                            {
                                                chunksBuffer[i].CopyTo(allPoints, offset);
                                                offset += chunksBuffer[i].Length;
                                            }

                                            latestPayload = new RoutePayload { type = "route", points = allPoints };
                                            hasNewData = true;
                                            chunksBuffer = null;
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning("Failed to parse route JSON telemetry: " + e.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning)
            {
                Debug.LogError("UDP receive thread error (Route): " + err.ToString());
            }
        }
    }

    void Update()
    {
        bool updateLine = false;
        RoutePayload payloadToDraw = null;

        lock (dataLock)
        {
            if (hasNewData)
            {
                payloadToDraw = latestPayload;
                hasNewData = false;
                updateLine = true;
            }
        }

        if (updateLine && payloadToDraw != null)
        {
            int pointCount = payloadToDraw.points != null ? payloadToDraw.points.Length : 0;
            lineRenderer.positionCount = pointCount;
            
            if (pointCount > 0)
            {
                for (int i = 0; i < pointCount; i++)
                {
                    RoutePoint pt = payloadToDraw.points[i];
                    // Unity maps SUMO X -> Unity X, SUMO Y -> Unity Z
                    Vector3 pos = new Vector3(pt.x, yOffset, pt.z);
                    lineRenderer.SetPosition(i, pos);
                }
                
                // Route endpoint directly on the road
                RoutePoint endPt = payloadToDraw.points[pointCount - 1];
                Vector3 endPos = new Vector3(endPt.x, yOffset, endPt.z);

                // Resolve destination hospital name from actual endpoint
                string hospitalName = ResolveDestinationName(endPt.x, endPt.z);

                // Update marker transform and label
                if (destinationMarkerRoot != null)
                {
                    destinationMarkerRoot.transform.localPosition = endPos;

                    if (destinationTextMesh != null)
                    {
                        destinationTextMesh.text = hospitalName.ToUpper();
                    }
                    if (destinationShadowMesh != null)
                    {
                        destinationShadowMesh.text = hospitalName.ToUpper();
                    }
                    if (billboardBackplate != null)
                    {
                        float panelWidth = Mathf.Clamp(hospitalName.Length * 0.95f, 10.0f, 26.0f);
                        billboardBackplate.transform.localScale = new Vector3(panelWidth, 3.2f, 0.3f);
                    }

                    destinationMarkerRoot.SetActive(true);
                }

                lastRouteTime = Time.time;
                Debug.Log($"RouteRenderer updated with {pointCount} points. Destination: {hospitalName} at ({endPt.x:F1}, {endPt.z:F1})");
            }
            else
            {
                if (destinationMarkerRoot != null) destinationMarkerRoot.SetActive(false);
            }
        }

        // Trip lifecycle check: remove or hide marker when trip completes or route is cleared
        if (destinationMarkerRoot != null && destinationMarkerRoot.activeSelf)
        {
            if (ambulanceTransform == null)
            {
                GameObject amb = GameObject.Find("Ambulance");
                if (amb != null) ambulanceTransform = amb.transform;
            }

            // Ambulance is sent to Y = -500 underground when trip completes/stops
            bool tripInactive = (ambulanceTransform != null && ambulanceTransform.position.y < -100f);
            bool routeTimedOut = (lastRouteTime > 0f && Time.time - lastRouteTime > 15.0f && ambulanceTransform == null);

            if (tripInactive || routeTimedOut)
            {
                destinationMarkerRoot.SetActive(false);
                lineRenderer.positionCount = 0;
            }
            else
            {
                // Billboard orientation: orient label towards active camera
                Camera cam = Camera.main;
                if (cam != null && billboardTransform != null)
                {
                    Vector3 dir = billboardTransform.position - cam.transform.position;
                    if (dir.sqrMagnitude > 0.01f)
                    {
                        billboardTransform.rotation = Quaternion.LookRotation(dir);
                    }
                }

                // Beacon pulsing animation
                if (beaconTransform != null)
                {
                    float pulse = 1.0f + 0.12f * Mathf.Sin(Time.time * 4.5f);
                    beaconTransform.localScale = new Vector3(1.6f * pulse, 1.6f * pulse, 1.6f * pulse);
                }
            }
        }
    }

    private string ResolveDestinationName(float endX, float endZ)
    {
        string bestName = "DESTINATION";
        float minDistance = float.MaxValue;

        if (cachedHospitals != null && cachedHospitals.Length > 0)
        {
            foreach (var h in cachedHospitals)
            {
                float dx = h.x - endX;
                float dz = h.y - endZ;
                float d = Mathf.Sqrt(dx * dx + dz * dz);
                if (d < minDistance)
                {
                    minDistance = d;
                    bestName = string.IsNullOrEmpty(h.name) ? h.id.Replace("_", " ").ToUpper() : h.name;
                }
            }
        }
        return bestName;
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
