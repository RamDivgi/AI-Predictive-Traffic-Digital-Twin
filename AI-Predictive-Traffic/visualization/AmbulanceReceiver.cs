using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

[System.Serializable]
public class TelemetryData
{
    public string id;
    public float x;
    public float y;
    public float z;
    public float angle;
    public float speed;
    public float sim_time;
}

public class AmbulanceReceiver : MonoBehaviour
{
    public int listenPort = 5005;
    
    // Smoothing parameters
    public float movementSmoothing = 10f;
    public float rotationSmoothing = 10f;

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;
    
    // Thread-safe buffer for the latest parsed telemetry
    private TelemetryData latestTelemetry;
    private object dataLock = new object();
    
    private float lastLogTime = 0f;

    private static AmbulanceReceiver instance;

    void Awake()
    {
        if (instance != null && instance != this)
        {
            Debug.LogWarning("Duplicate AmbulanceReceiver detected! Destroying the duplicate component.");
            Destroy(this);
            return;
        }
        instance = this;
    }

    void Start()
    {
        Debug.Log("AmbulanceReceiver instance active: 1");
        CreateAmbulanceModel();
        // Start the UDP listener on a background thread so it doesn't block Unity
        StartUDPReceiver();
    }

    private void CreateAmbulanceModel()
    {
        // Remove existing renderer/collider if this was previously a basic cube
        if (GetComponent<Renderer>()) Destroy(GetComponent<Renderer>());
        if (GetComponent<MeshFilter>()) Destroy(GetComponent<MeshFilter>());
        if (GetComponent<Collider>()) Destroy(GetComponent<Collider>());

        // Base Body (White)
        GameObject body = GameObject.CreatePrimitive(PrimitiveType.Cube);
        body.name = "Body";
        body.transform.parent = this.transform;
        body.transform.localPosition = new Vector3(0, 1.25f, 0); // elevated to sit on wheels/road
        body.transform.localScale = new Vector3(2.0f, 2.5f, 5.5f);
        Destroy(body.GetComponent<Collider>());
        
        Material whiteMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        whiteMat.color = Color.white;
        body.GetComponent<Renderer>().material = whiteMat;

        // Front cab (slightly lower)
        GameObject cab = GameObject.CreatePrimitive(PrimitiveType.Cube);
        cab.name = "Cab";
        cab.transform.parent = this.transform;
        cab.transform.localPosition = new Vector3(0, 1.0f, 2.75f);
        cab.transform.localScale = new Vector3(2.0f, 1.5f, 1.5f);
        Destroy(cab.GetComponent<Collider>());
        cab.GetComponent<Renderer>().material = whiteMat;

        Material redMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        redMat.color = Color.red;

        // Red Cross - Left Side
        CreateCross(new Vector3(-1.01f, 1.4f, 0), Vector3.right, redMat);
        // Red Cross - Right Side
        CreateCross(new Vector3(1.01f, 1.4f, 0), Vector3.left, redMat);
        // Red Cross - Roof
        CreateCross(new Vector3(0, 2.51f, 0), Vector3.up, redMat);

        // Emergency Light Bar (Blue/Red)
        GameObject lightBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        lightBar.name = "LightBar";
        lightBar.transform.parent = this.transform;
        lightBar.transform.localPosition = new Vector3(0, 2.6f, 1.5f);
        lightBar.transform.localScale = new Vector3(1.5f, 0.2f, 0.5f);
        Destroy(lightBar.GetComponent<Collider>());
        
        Material lightMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        lightMat.color = Color.blue;
        lightMat.EnableKeyword("_EMISSION");
        lightMat.SetColor("_EmissionColor", Color.blue * 2f);
        lightBar.GetComponent<Renderer>().material = lightMat;

        // Wheels
        Material blackMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        blackMat.color = Color.black;
        CreateWheel(new Vector3(-1.0f, 0.4f, 1.5f), blackMat);
        CreateWheel(new Vector3(1.0f, 0.4f, 1.5f), blackMat);
        CreateWheel(new Vector3(-1.0f, 0.4f, -1.5f), blackMat);
        CreateWheel(new Vector3(1.0f, 0.4f, -1.5f), blackMat);

        // Text Labels
        CreateTextLabel(new Vector3(-1.01f, 1.9f, 0), "AMBULANCE", -90f);
        CreateTextLabel(new Vector3(1.01f, 1.9f, 0), "AMBULANCE", 90f);
    }

    private void CreateWheel(Vector3 pos, Material mat)
    {
        GameObject wheel = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        wheel.name = "Wheel";
        wheel.transform.parent = this.transform;
        wheel.transform.localPosition = pos;
        wheel.transform.localRotation = Quaternion.Euler(0, 0, 90f);
        wheel.transform.localScale = new Vector3(0.8f, 0.2f, 0.8f);
        Destroy(wheel.GetComponent<Collider>());
        wheel.GetComponent<Renderer>().material = mat;
    }

    private void CreateTextLabel(Vector3 pos, string text, float yRot)
    {
        GameObject txtObj = new GameObject("Label");
        txtObj.transform.parent = this.transform;
        txtObj.transform.localPosition = pos;
        txtObj.transform.localRotation = Quaternion.Euler(0, yRot, 0);
        TextMesh tm = txtObj.AddComponent<TextMesh>();
        tm.text = text;
        tm.characterSize = 0.1f;
        tm.fontSize = 48;
        tm.color = Color.red;
        tm.anchor = TextAnchor.MiddleCenter;
        tm.alignment = TextAlignment.Center;
    }

    private void CreateCross(Vector3 position, Vector3 normal, Material mat)
    {
        // Vertical bar
        GameObject vBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        vBar.transform.parent = this.transform;
        vBar.transform.localPosition = position;
        vBar.transform.localRotation = Quaternion.LookRotation(normal);
        vBar.transform.localScale = new Vector3(0.8f, 0.8f, 0.1f);
        Destroy(vBar.GetComponent<Collider>());
        vBar.GetComponent<Renderer>().material = mat;

        // We can just use a slightly wider cube and a taller cube
        vBar.transform.localScale = new Vector3(0.3f, 1.0f, 0.05f);

        // Horizontal bar
        GameObject hBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        hBar.transform.parent = this.transform;
        hBar.transform.localPosition = position;
        hBar.transform.localRotation = Quaternion.LookRotation(normal);
        hBar.transform.localScale = new Vector3(1.0f, 0.3f, 0.05f);
        Destroy(hBar.GetComponent<Collider>());
        hBar.GetComponent<Renderer>().material = mat;
    }

    private void StartUDPReceiver()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("AmbulanceReceiver: Started UDP listener on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            while (isRunning)
            {
                // Block until a message is received
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);
                
                // Parse JSON
                try 
                {
                    TelemetryData telemetry = JsonUtility.FromJson<TelemetryData>(text);
                    
                    if (telemetry != null && telemetry.id == "ambulance")
                    {
                        // Thread-safe assignment
                        lock(dataLock)
                        {
                            latestTelemetry = telemetry;
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning("Failed to parse JSON telemetry: " + e.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning)
            {
                Debug.LogError("UDP receive thread error: " + err.ToString());
            }
        }
    }

    void Update()
    {
        TelemetryData telemetry = null;
        
        lock(dataLock)
        {
            if (latestTelemetry != null)
            {
                // Clone the data to use in the main thread
                telemetry = new TelemetryData
                {
                    id = latestTelemetry.id,
                    x = latestTelemetry.x,
                    y = latestTelemetry.y,
                    z = latestTelemetry.z,
                    angle = latestTelemetry.angle,
                    speed = latestTelemetry.speed,
                    sim_time = latestTelemetry.sim_time
                };
            }
        }

        if (telemetry != null)
        {
            // The coordinate mapping (SUMO to Unity) is already done in the Python bridge!
            // Python sends: x=SUMO_X, y=0, z=SUMO_Y, angle=SUMO_Angle
            Vector3 targetPosition = new Vector3(telemetry.x, telemetry.y, telemetry.z);
            
            // Convert angle to Quaternion
            // SUMO 0 angle is North (Unity Z+), and angles increase clockwise.
            // Unity rotation on Y axis matches this.
            Quaternion targetRotation = Quaternion.Euler(0, telemetry.angle, 0);

            // Interpolate for smooth visual movement, eliminating "stutter" 
            // caused by discrete Python bridge steps.
            transform.position = Vector3.Lerp(transform.position, targetPosition, Time.deltaTime * movementSmoothing);
            transform.rotation = Quaternion.Lerp(transform.rotation, targetRotation, Time.deltaTime * rotationSmoothing);

            // Log at a reasonable interval (e.g. every 2 seconds) to avoid flooding the console
            if (Time.time - lastLogTime >= 2.0f)
            {
                Debug.Log($"Ambulance position received. Unity position: X={transform.position.x:F2}, Y={transform.position.y:F2}, Z={transform.position.z:F2}");
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
