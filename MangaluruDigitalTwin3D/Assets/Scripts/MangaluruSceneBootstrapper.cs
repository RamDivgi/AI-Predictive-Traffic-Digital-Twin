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

        // VisualizationSystems owns communication receivers only.  The scene's
        // RoadNetwork object owns the sole RoadVisualizer instance.
        GameObject visSys = GetOrCreate("VisualizationSystems", root.transform);

        RoadVisualizer roadVisualizer = Object.FindFirstObjectByType<RoadVisualizer>();
        if (roadVisualizer == null)
        {
            Debug.LogError("MangaluruSceneBootstrapper: SampleScene must contain exactly one RoadVisualizer on RoadNetwork.");
        }
        else
        {
            RemoveDuplicateComponents(roadVisualizer);
        }

        // Keep exactly one receiver for each Unity/SUMO channel.  The ambulance
        // receiver belongs to the Ambulance because it moves that transform.
        EnsureSingleComponent<TrafficReceiver>(visSys);
        EnsureSingleComponent<TrafficSignalReceiver>(visSys);
        EnsureSingleComponent<RouteReceiver>(visSys);
        EnsureSingleComponent<AmbulanceReceiver>(ambulance);

        // Hospitals are a separate visual subsystem and are never created by
        // RoadVisualizer.  This object is their single owner.
        EnsureSingleComponent<HospitalVisualizer>(hospital);

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
        AmbulanceCameraFollow camFollow = EnsureSingleComponent<AmbulanceCameraFollow>(mainCam.gameObject);
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

    private static T EnsureSingleComponent<T>(GameObject owner) where T : Behaviour
    {
        T[] components = Object.FindObjectsByType<T>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        T retained = owner.GetComponent<T>();

        foreach (T component in components)
        {
            if (component == retained)
            {
                continue;
            }

            // Disable immediately so a duplicate cannot initialize this frame,
            // then remove it normally at the end of the frame.
            component.enabled = false;
            Object.Destroy(component);
        }

        return retained != null ? retained : owner.AddComponent<T>();
    }

    private static void RemoveDuplicateComponents<T>(T retained) where T : Behaviour
    {
        T[] components = Object.FindObjectsByType<T>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (T component in components)
        {
            if (component == retained)
            {
                continue;
            }

            component.enabled = false;
            Object.Destroy(component);
        }
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
