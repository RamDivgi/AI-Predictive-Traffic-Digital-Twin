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
    public float yOffset = 0.1f; // Slightly above road surface
    public float lineWidth = 0.15f; // Thin navigation line
    public Color routeColor = new Color(0.4f, 0.8f, 1.0f, 1.0f); // Light blue

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

    void Start()
    {
        InitializeLineRenderer();
        StartUDPReceiver();
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
            int pointCount = payloadToDraw.points.Length;
            lineRenderer.positionCount = pointCount;
            
            for (int i = 0; i < pointCount; i++)
            {
                RoutePoint pt = payloadToDraw.points[i];
                // Unity maps SUMO X -> Unity X, SUMO Y -> Unity Z
                Vector3 pos = new Vector3(pt.x, yOffset, pt.z);
                lineRenderer.SetPosition(i, pos);
            }
            
            Debug.Log($"RouteRenderer updated with {pointCount} points.");
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
