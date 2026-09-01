using UnityEngine;

public static class MangaluruSceneBootstrapper
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    public static void InitializeScene()
    {
        Debug.Log("MangaluruSceneBootstrapper: Verifying and assembling required hierarchy...");

        // Root
        GameObject root = GetOrCreate("MangaluruDigitalTwin");

        // Environment
        GameObject env = GetOrCreate("Environment", root.transform);
        GetOrCreate("Roads", env.transform);
        GetOrCreate("Buildings", env.transform);
        GetOrCreate("Intersections", env.transform);

        // Traffic
        GameObject traffic = GetOrCreate("Traffic", root.transform);
        GetOrCreate("Vehicles", traffic.transform);
        GetOrCreate("TrafficSignals", traffic.transform);

        // Emergency
        GameObject emergency = GetOrCreate("Emergency", root.transform);
        GameObject ambulance = GetOrCreate("Ambulance", emergency.transform);
        BuildProceduralAmbulance(ambulance);

        // Destinations
        GameObject destinations = GetOrCreate("Destinations", root.transform);
        GameObject hospital = GetOrCreate("HighlandHospital", destinations.transform);

        // VisualizationSystems
        GameObject visSys = GetOrCreate("VisualizationSystems", root.transform);
        
        // Attach Scripts
        EnsureComponent<RoadVisualizer>(visSys);
        EnsureComponent<TrafficReceiver>(visSys);
        EnsureComponent<TrafficSignalReceiver>(visSys);
        EnsureComponent<RouteReceiver>(visSys);
        
        // Purge any stale AmbulanceReceivers (e.g. from previous manual setups)
        AmbulanceReceiver[] oldReceivers = Object.FindObjectsByType<AmbulanceReceiver>(FindObjectsSortMode.None);
        foreach (var r in oldReceivers)
        {
            Object.DestroyImmediate(r);
        }

        // Ambulance Receiver should be on the Ambulance object to directly move it, 
        // or if it's on VisualizationSystems, it needs to know what to move. 
        // In previous code, AmbulanceReceiver used 'this.transform'. So it must be on Ambulance.
        EnsureComponent<AmbulanceReceiver>(ambulance);
        
        // Hospital Visualizer builds the hospital at its location, can be on the hospital object
        EnsureComponent<HospitalVisualizer>(hospital);

        // Main Camera
        Camera mainCam = Camera.main;
        if (mainCam == null)
        {
            GameObject camObj = new GameObject("Main Camera");
            camObj.tag = "MainCamera";
            mainCam = camObj.AddComponent<Camera>();
        }
        mainCam.transform.parent = root.transform;
        
        // Ensure Camera Follow is attached
        AmbulanceCameraFollow camFollow = EnsureComponent<AmbulanceCameraFollow>(mainCam.gameObject);
        camFollow.target = ambulance.transform;

        Debug.Log("MangaluruSceneBootstrapper: Scene assembly complete.");
    }

    private static GameObject GetOrCreate(string name, Transform parent = null)
    {
        GameObject go = GameObject.Find(name);
        if (go == null)
        {
            // If there's a parent, try to find a child with that name first
            if (parent != null)
            {
                Transform child = parent.Find(name);
                if (child != null) return child.gameObject;
            }
            
            go = new GameObject(name);
        }
        
        if (parent != null)
        {
            go.transform.SetParent(parent);
        }
        return go;
    }

    private static T EnsureComponent<T>(GameObject go) where T : Component
    {
        T comp = go.GetComponent<T>();
        if (comp == null)
        {
            comp = go.AddComponent<T>();
        }
        return comp;
    }

    private static void BuildProceduralAmbulance(GameObject ambulance)
    {
        // 1. Setup Root Component
        EnsureComponent<VehicleSmoother>(ambulance);

        // 2. Clean up old problematic meshes
        Transform oldElora = ambulance.transform.Find("EloraWhite(Clone)");
        if (oldElora != null) Object.DestroyImmediate(oldElora.gameObject);

        // Destroy placeholder meshes on root
        if (ambulance.GetComponent<MeshRenderer>()) Object.DestroyImmediate(ambulance.GetComponent<MeshRenderer>());
        if (ambulance.GetComponent<MeshFilter>()) Object.DestroyImmediate(ambulance.GetComponent<MeshFilter>());
        if (ambulance.GetComponent<Collider>()) Object.DestroyImmediate(ambulance.GetComponent<Collider>());

        // 3. Establish the strict Visual wrapper
        Transform visualWrapper = ambulance.transform.Find("AmbulanceVisual");
        GameObject visualObj;
        if (visualWrapper == null)
        {
            visualObj = new GameObject("AmbulanceVisual");
            visualObj.transform.SetParent(ambulance.transform);
        }
        else
        {
            visualObj = visualWrapper.gameObject;
        }

        // Clean out any old children in the visual wrapper
        for (int i = visualObj.transform.childCount - 1; i >= 0; i--)
        {
            Object.DestroyImmediate(visualObj.transform.GetChild(i).gameObject);
        }

        // Align visual perfectly to root. No rotations needed since we build native +Z!
        visualObj.transform.localPosition = Vector3.zero;
        visualObj.transform.localRotation = Quaternion.identity;

        // 4. Load the proper Ambulance Prefab
        GameObject prefab = Resources.Load<GameObject>("Cars/AmbulancePrefab");
        if (prefab != null)
        {
            GameObject newAmbulance = Object.Instantiate(prefab, visualObj.transform);
            newAmbulance.name = "AmbulancePrefab";
            
            // Dimensional Verification:
            // Ambulance.glb length is 20.09m. Target realistic length is ~5.0m (matching normal cars).
            // Required scale: 5.0 / 20.09 = ~0.25
            visualObj.transform.localScale = new Vector3(0.25f, 0.25f, 0.25f);
            
            // Orientation Verification:
            // Ambulance.glb length aligns with Z-axis and inherently points forward (+Z).
            // No rotation hacks needed.
            visualObj.transform.localRotation = Quaternion.identity;
            
            // Pivot Verification:
            // The model's origin is roughly 1m from the rear bumper, aligning perfectly with standard rear-axle pivot setups.
            visualObj.transform.localPosition = Vector3.zero;
        }
        else
        {
            Debug.LogWarning("Ambulance model not assigned. AmbulanceVisual is waiting for Assets/Resources/Cars/AmbulancePrefab.glb");
        }
        
        visualObj.SetActive(true);
    }
}
