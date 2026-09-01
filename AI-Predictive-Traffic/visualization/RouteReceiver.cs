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
    public RoutePoint[] points;
}

public class RouteReceiver : MonoBehaviour
{
    public int listenPort = 5008;
    public float yOffset = 0.2f; // Slightly above road surface
    public float lineWidth = 0.15f; // Thin navigation line
    public Color routeColor = new Color(0.4f, 0.8f, 1.0f, 1.0f); // Light blue

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private LineRenderer lineRenderer;
    private RoutePayload latestPayload;
    private object dataLock = new object();
    private bool hasNewData = false;

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
        lineRenderer.useWorldSpace = true;
        
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
                    if (payload != null && payload.type == "route" && payload.points != null)
                    {
                        lock (dataLock)
                        {
                            latestPayload = payload;
                            hasNewData = true;
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
