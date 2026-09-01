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

    void Start()
    {
        // Disable any placeholder mesh on this object
        MeshRenderer mr = GetComponent<MeshRenderer>();
        if (mr != null) mr.enabled = false;

        // Load a realistic SUV model for the ambulance
        // (Removed duplicate instantiation of EloraWhite as AmbulanceVisual. The intended visual is now managed entirely by MangaluruSceneBootstrapper)

        // Start the UDP listener on a background thread so it doesn't block Unity
        StartUDPReceiver();
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
                
                // Clear the buffer so we don't process stale data if connection stops
                latestTelemetry = null;
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

            // Send data to the proven VehicleSmoother architecture instead of broken manual lerping
            VehicleSmoother smoother = GetComponent<VehicleSmoother>();
            if (smoother == null)
            {
                smoother = gameObject.AddComponent<VehicleSmoother>();
            }
            smoother.UpdateTarget(targetPosition, targetRotation);

            // Log at a reasonable interval (e.g. every 2 seconds) to avoid flooding the console
            if (Time.time - lastLogTime >= 2.0f)
            {
                Debug.Log($"\n[AMBULANCE DEBUG]\n" +
                          $"SUMO=({telemetry.x:F2}, {telemetry.y:F2}, {telemetry.z:F2})\n" +
                          $"UNITY_CONVERTED=({targetPosition.x:F2}, {targetPosition.y:F2}, {targetPosition.z:F2})\n" +
                          $"FINAL_TRANSFORM=(Pos:{transform.position} | LocalPos:{transform.localPosition} | Rot:{transform.rotation.eulerAngles} | LocalScale:{transform.localScale})\n");
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
