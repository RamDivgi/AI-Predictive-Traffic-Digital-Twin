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
