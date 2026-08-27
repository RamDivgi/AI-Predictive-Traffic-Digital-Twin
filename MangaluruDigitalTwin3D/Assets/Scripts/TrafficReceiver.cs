using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

[System.Serializable]
public class TrafficPayload
{
    public TelemetryData[] vehicles;
}

public class TrafficReceiver : MonoBehaviour
{
    public int listenPort = 5006;
    public float movementSmoothing = 10f;
    public float rotationSmoothing = 10f;
    
    // Configurable maximum number of vehicles (0 = unlimited)
    public int maxVehicles = 500;
    public Material vehicleMaterial;

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private TrafficPayload latestPayload;
    private object dataLock = new object();

    // Dictionary to track active vehicle game objects
    private Dictionary<string, GameObject> activeVehicles = new Dictionary<string, GameObject>();
    
    private int packetsReceived = 0;
    private float lastLogTime = 0f;

    void Start()
    {
        StartUDPReceiver();
    }

    private void StartUDPReceiver()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("TrafficReceiver: Started UDP listener on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            // Increase receive buffer size for larger JSON arrays
            udpClient.Client.ReceiveBufferSize = 65535 * 4;

            while (isRunning)
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);

                try
                {
                    TrafficPayload payload = JsonUtility.FromJson<TrafficPayload>(text);

                    if (payload != null && payload.vehicles != null)
                    {
                        lock (dataLock)
                        {
                            latestPayload = payload;
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning("Failed to parse traffic JSON: " + e.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning)
            {
                Debug.LogError("UDP receive thread error (Traffic): " + err.ToString());
            }
        }
    }

    void Update()
    {
        TrafficPayload payload = null;

        lock (dataLock)
        {
            if (latestPayload != null)
            {
                payload = latestPayload;
                // Clear so we don't process the same payload repeatedly if simulation is paused
                latestPayload = null; 
            }
        }

        if (payload != null && payload.vehicles != null)
        {
            HashSet<string> currentFrameVehicleIDs = new HashSet<string>();

            int count = 0;
            foreach (TelemetryData v in payload.vehicles)
            {
                if (maxVehicles > 0 && count >= maxVehicles) break;

                currentFrameVehicleIDs.Add(v.id);

                Vector3 targetPos = new Vector3(v.x, v.y + 0.75f, v.z);
                Quaternion targetRot = Quaternion.Euler(0, v.angle, 0);

                if (activeVehicles.ContainsKey(v.id))
                {
                    // Update existing vehicle
                    GameObject vehObj = activeVehicles[v.id];
                    vehObj.transform.position = Vector3.Lerp(vehObj.transform.position, targetPos, Time.deltaTime * movementSmoothing);
                    vehObj.transform.rotation = Quaternion.Lerp(vehObj.transform.rotation, targetRot, Time.deltaTime * rotationSmoothing);
                }
                else
                {
                    // Create new vehicle procedural model
                    GameObject vehObj = CreateProceduralVehicle(v.id);
                    
                    GameObject vehParent = GameObject.Find("Traffic/Vehicles");
                    vehObj.transform.parent = (vehParent != null) ? vehParent.transform : this.transform;
                    
                    vehObj.transform.position = targetPos;
                    vehObj.transform.rotation = targetRot;

                    activeVehicles.Add(v.id, vehObj);
                }
                
                count++;
            }

            // Remove vehicles that left the SUMO simulation
            List<string> toRemove = new List<string>();
            foreach (var kvp in activeVehicles)
            {
                if (!currentFrameVehicleIDs.Contains(kvp.Key))
                {
                    toRemove.Add(kvp.Key);
                    Destroy(kvp.Value);
                }
            }

            foreach (string id in toRemove)
            {
                activeVehicles.Remove(id);
            }
            
            packetsReceived++;
            if (Time.time - lastLogTime >= 5.0f)
            {
                string firstVehPos = activeVehicles.Count > 0 ? activeVehicles[new List<string>(activeVehicles.Keys)[0]].transform.position.ToString() : "None";
                Debug.Log($"TrafficReceiver: Packets received: {packetsReceived} | Active Unity vehicles: {activeVehicles.Count}");
                Debug.Log($"Traffic visual check: Active vehicles = {activeVehicles.Count} | First vehicle position = {firstVehPos}");
                lastLogTime = Time.time;
            }
        }
    }

    private GameObject CreateProceduralVehicle(string id)
    {
        GameObject root = new GameObject("Vehicle_" + id);
        
        // Deterministic variation based on ID
        int hash = Mathf.Abs(id.GetHashCode());
        int vehicleType = hash % 4; // 0=Sedan, 1=Hatchback, 2=SUV, 3=Truck
        
        Color[] colors = new Color[] {
            Color.red, Color.blue, new Color(0.1f, 0.6f, 0.1f), 
            Color.yellow, new Color(0.8f, 0.8f, 0.8f), 
            new Color(0.2f, 0.2f, 0.2f), Color.white 
        };
        Color vColor = colors[(hash / 4) % colors.Length];
        
        Material mat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        mat.color = vColor;
        
        Material glassMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        glassMat.color = new Color(0.1f, 0.1f, 0.1f);
        
        if (vehicleType == 0) // Sedan
        {
            CreatePart(root, "Body", new Vector3(0, 0.4f, 0), new Vector3(1.8f, 0.8f, 4.2f), mat);
            CreatePart(root, "Cabin", new Vector3(0, 1.0f, -0.2f), new Vector3(1.6f, 0.6f, 2.0f), glassMat);
        }
        else if (vehicleType == 1) // Hatchback
        {
            CreatePart(root, "Body", new Vector3(0, 0.4f, 0), new Vector3(1.8f, 0.8f, 3.6f), mat);
            CreatePart(root, "Cabin", new Vector3(0, 1.0f, -0.5f), new Vector3(1.6f, 0.7f, 1.8f), glassMat);
        }
        else if (vehicleType == 2) // SUV
        {
            CreatePart(root, "Body", new Vector3(0, 0.6f, 0), new Vector3(2.0f, 1.0f, 4.5f), mat);
            CreatePart(root, "Cabin", new Vector3(0, 1.3f, -0.4f), new Vector3(1.8f, 0.8f, 2.5f), glassMat);
        }
        else // Truck
        {
            CreatePart(root, "Cab", new Vector3(0, 0.8f, 1.5f), new Vector3(2.2f, 1.6f, 1.8f), mat);
            CreatePart(root, "Bed", new Vector3(0, 0.6f, -1.0f), new Vector3(2.2f, 1.2f, 3.2f), new Material(Shader.Find("Universal Render Pipeline/Lit")) { color = Color.gray });
        }
        
        return root;
    }

    private void CreatePart(GameObject parent, string name, Vector3 pos, Vector3 scale, Material mat)
    {
        GameObject part = GameObject.CreatePrimitive(PrimitiveType.Cube);
        part.name = name;
        part.transform.parent = parent.transform;
        part.transform.localPosition = pos;
        part.transform.localScale = scale;
        Destroy(part.GetComponent<Collider>()); // optimize
        part.GetComponent<Renderer>().material = mat;
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
