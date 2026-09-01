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
    public int maxVehicles = 500;
    
    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private TrafficPayload latestPayload;
    private object dataLock = new object();

    private Queue<GameObject> vehiclePool = new Queue<GameObject>();
    private Dictionary<string, GameObject> activeVehicles = new Dictionary<string, GameObject>();
    private Dictionary<string, VehicleSmoother> activeSmoothers = new Dictionary<string, VehicleSmoother>();
    
    private int packetsReceived = 0;
    private float lastLogTime = 0f;

    private GameObject[] carPrefabs;

    void Start()
    {
        InitializeAssets();
        StartUDPReceiver();
    }

    private void InitializeAssets()
    {
        // Load the prefabs copied from SUMO2Unity
        carPrefabs = new GameObject[]
        {
            Resources.Load<GameObject>("Cars/AlmaBlue"),
            Resources.Load<GameObject>("Cars/AlmaGrey"),
            Resources.Load<GameObject>("Cars/ElkaBlack"),
            Resources.Load<GameObject>("Cars/ElkaRed"),
            Resources.Load<GameObject>("Cars/EloraGold"),
            Resources.Load<GameObject>("Cars/EloraWhite")
        };
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
            if (isRunning) Debug.LogError("UDP receive thread error (Traffic): " + err.ToString());
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

                Vector3 targetPos = new Vector3(v.x, v.y, v.z);
                Quaternion targetRot = Quaternion.Euler(0, v.angle, 0);

                if (activeSmoothers.TryGetValue(v.id, out VehicleSmoother smoother))
                {
                    smoother.UpdateTarget(targetPos, targetRot);
                }
                else
                {
                    GameObject vehObj = GetOrCreateVehicle(v.id);
                    VehicleSmoother newSmoother = vehObj.GetComponent<VehicleSmoother>();
                    newSmoother.UpdateTarget(targetPos, targetRot);
                    activeVehicles.Add(v.id, vehObj);
                    activeSmoothers.Add(v.id, newSmoother);
                }
                
                if (v.id == "car_0" && (Time.time - lastLogTime >= 2.0f))
                {
                    GameObject carObj = activeVehicles[v.id];
                    Debug.Log($"\n[VEHICLE DEBUG]\n" +
                              $"ID={v.id}\n" +
                              $"SUMO=({v.x:F2}, {v.y:F2}, {v.z:F2})\n" +
                              $"UNITY_CONVERTED=({targetPos.x:F2}, {targetPos.y:F2}, {targetPos.z:F2})\n" +
                              $"FINAL_TRANSFORM=(Pos:{carObj.transform.position} | LocalPos:{carObj.transform.localPosition} | Rot:{carObj.transform.rotation.eulerAngles} | LocalScale:{carObj.transform.localScale})\n");
                }
                
                count++;
            }

            List<string> toRemove = new List<string>();
            foreach (var kvp in activeVehicles)
            {
                if (!currentFrameVehicleIDs.Contains(kvp.Key))
                {
                    toRemove.Add(kvp.Key);
                    kvp.Value.SetActive(false);
                    vehiclePool.Enqueue(kvp.Value);
                }
            }

            foreach (string id in toRemove)
            {
                activeVehicles.Remove(id);
                activeSmoothers.Remove(id);
            }
            
            packetsReceived++;
            if (Time.time - lastLogTime >= 15.0f)
            {
                Debug.Log($"TrafficReceiver: Active Unity vehicles: {activeVehicles.Count} | Pooled: {vehiclePool.Count}");
                lastLogTime = Time.time;
            }
        }
    }

    private GameObject GetOrCreateVehicle(string id)
    {
        GameObject vehObj;
        if (vehiclePool.Count > 0)
        {
            vehObj = vehiclePool.Dequeue();
            vehObj.name = "Vehicle_" + id;
            vehObj.SetActive(true);
            vehObj.GetComponent<VehicleSmoother>().ResetState();
            return vehObj;
        }

        // Create new
        vehObj = new GameObject("Vehicle_" + id);
        GameObject vehParent = GameObject.Find("Traffic/Vehicles") ?? this.gameObject;
        vehObj.transform.parent = vehParent.transform;
        
        vehObj.AddComponent<VehicleSmoother>();

        int hash = Mathf.Abs(id.GetHashCode());
        GameObject prefab = carPrefabs[hash % carPrefabs.Length];
        if (prefab != null)
        {
            GameObject mesh = Instantiate(prefab, vehObj.transform);
            mesh.SetActive(true);
            // Model Normalization: Imported cars often natively face the X-axis and pivot at the rear/center.
            // SUMO provides the coordinate for the front bumper.
            mesh.transform.localScale = Vector3.one; 
            mesh.transform.localPosition = new Vector3(0, 0, -2.1f); // Shift mesh backward to align front bumper with root
            mesh.transform.localRotation = Quaternion.Euler(0, -90f, 0); // Rotate mesh so native X-forward faces root's Z-forward
            // Remove physics interference since SUMO controls movement
            foreach (var rb in mesh.GetComponentsInChildren<Rigidbody>())
            {
                Destroy(rb);
            }
        }

        return vehObj;
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (receiveThread != null && receiveThread.IsAlive) receiveThread.Abort();
        if (udpClient != null) udpClient.Close();
    }
}
