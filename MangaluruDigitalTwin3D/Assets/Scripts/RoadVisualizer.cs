using UnityEngine;
using System.IO;
using System.Collections.Generic;

[System.Serializable]
public class Point2D {
    public float x;
    public float y;
}

[System.Serializable]
public class LaneData {
    public string id;
    public float width;
    public Point2D[] shape;
}

[System.Serializable]
public class EdgeData {
    public string id;
    public LaneData[] lanes;
}

[System.Serializable]
public class JunctionData {
    public string id;
    public float x;
    public float y;
    public Point2D[] shape;
}

[System.Serializable]
public class TlsLinkData {
    public int link_index;
    public string from_lane;
    public string to_lane;
    public string junction;
}

[System.Serializable]
public class TlsData {
    public string id;
    public float x;
    public float y;
    public string[] controlled_junctions;
    public TlsLinkData[] controlled_links;
}

[System.Serializable]
public class BuildingData {
    public string id;
    public Point2D[] shape;
}

[System.Serializable]
public class HospitalData {
    public string id;
    public string name;
    public float x;
    public float y;
}

[System.Serializable]
public class RoadLabelData {
    public string name;
    public float x;
    public float y;
}

[System.Serializable]
public class RoadNetworkData {
    public EdgeData[] edges;
    public JunctionData[] junctions;
    public BuildingData[] buildings;
    public HospitalData[] hospitals;
    public RoadLabelData[] road_labels;
    public TlsData[] traffic_lights;
}

public class RoadVisualizer : MonoBehaviour
{
    public string jsonFileName = "RoadNetwork.json";
    public Material roadMaterial;
    public float defaultLineWidth = 3.2f; // Standard lane width

    private bool hasRendered;
    
    private Dictionary<string, GameObject> allTlsRoots = new Dictionary<string, GameObject>();
    private Dictionary<string, HashSet<string>> tlsToIncomingEdges = new Dictionary<string, HashSet<string>>();
    private Dictionary<string, Vector3[]> edgeShapes = new Dictionary<string, Vector3[]>();

    void Start()
    {
        if (hasRendered) return;
        hasRendered = true;
        LoadAndRenderRoads();
    }

    void LoadAndRenderRoads()
    {
        string filePath = Path.Combine(Application.dataPath, "Generated", jsonFileName);
        
        if (!File.Exists(filePath))
        {
            Debug.LogError("RoadNetwork.json not found at: " + filePath);
            return;
        }

        string jsonContent = File.ReadAllText(filePath);
        RoadNetworkData networkData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);

        if (networkData == null || networkData.edges == null)
        {
            Debug.LogError("Failed to parse RoadNetworkData.");
            return;
        }

        /*
         * COORDINATE SYSTEM DOCUMENTATION:
         * 
         * SUMO uses a 2D Cartesian plane (X, Y).
         * Unity uses a 3D Left-Handed system (X, Y, Z).
         * 
         * To ensure alignment with AmbulanceReceiver.cs:
         * 1. Unity.X = SUMO.X
         * 2. Unity.Y = 0 (Ground plane)
         * 3. Unity.Z = SUMO.Y
         * 
         * Scale Factor: 1.0 (1 SUMO meter = 1 Unity unit)
         * Origin/Reference: Shared (0,0,0) in Unity corresponds to (0,0) in SUMO.
         */

        GameObject roadsParent = GameObject.Find("Environment/Roads");
        if (roadsParent == null) roadsParent = new GameObject("SUMO_Roads");

        Material mat = roadMaterial;
        if (mat == null)
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader != null) {
                mat = new Material(shader);
                mat.color = new Color(0.2f, 0.2f, 0.2f); // Dark gray for roads
            }
        }
        
        // Create a massive ground plane to anchor the city visually
        GameObject ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "CityGround";
        ground.transform.parent = roadsParent.transform;
        ground.transform.localPosition = new Vector3(2000f, -0.1f, 1500f); // Center of typical Mangaluru coords
        ground.transform.localScale = new Vector3(1000f, 1f, 1000f); // 10km x 10km
        Material groundMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        groundMat.color = new Color(0.15f, 0.2f, 0.15f); // Dark greenish-gray base
        ground.GetComponent<Renderer>().material = groundMat;
        Destroy(ground.GetComponent<Collider>()); // Don't need physics for ground
        
        Material markingMat = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
        markingMat.color = Color.white;
        
        Material solidMarkingMat = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
        solidMarkingMat.color = Color.white;
        
        // Generate a dashed texture
        Texture2D dashedTex = new Texture2D(64, 4);
        dashedTex.filterMode = FilterMode.Point;
        for (int y = 0; y < 4; y++) {
            for (int x = 0; x < 64; x++) {
                dashedTex.SetPixel(x, y, x < 32 ? Color.white : Color.clear);
            }
        }
        dashedTex.Apply();
        markingMat.mainTexture = dashedTex;

        foreach (EdgeData edge in networkData.edges)
        {
            foreach (LaneData lane in edge.lanes)
            {
                if (lane.shape == null || lane.shape.Length < 2) continue;

                GameObject laneObj = new GameObject("Lane_" + lane.id);
                laneObj.transform.parent = roadsParent.transform;
                laneObj.isStatic = true;

                MeshFilter meshFilter = laneObj.AddComponent<MeshFilter>();
                MeshRenderer meshRenderer = laneObj.AddComponent<MeshRenderer>();
                
                meshRenderer.material = mat;

                float width = lane.width > 0 ? lane.width : defaultLineWidth;
                
                Mesh mesh = GenerateLaneMesh(lane.shape, width);
                meshFilter.mesh = mesh;
                
                // Add center lane marking
                GameObject markingObj = new GameObject("Marking_" + lane.id);
                markingObj.transform.parent = laneObj.transform;
                LineRenderer lr = markingObj.AddComponent<LineRenderer>();
                lr.positionCount = lane.shape.Length;
                lr.startWidth = 0.15f;
                lr.endWidth = 0.15f;
                lr.material = markingMat;
                lr.useWorldSpace = false;
                lr.textureMode = LineTextureMode.Tile;
                
                float totalDistance = 0f;
                for (int i = 0; i < lane.shape.Length; i++)
                {
                    Vector3 pos = new Vector3(lane.shape[i].x, 0.05f, lane.shape[i].y);
                    lr.SetPosition(i, pos);
                    
                    if (i > 0)
                    {
                        Vector3 prevPos = new Vector3(lane.shape[i-1].x, 0.05f, lane.shape[i-1].y);
                        totalDistance += Vector3.Distance(prevPos, pos);
                    }
                }
                
                // Tile the texture based on distance to make it look dashed
                // Approx 2 dashes per meter
                lr.material.mainTextureScale = new Vector2(totalDistance / 2f, 1f);
                
                // Add solid edge markings
                for (int m = -1; m <= 1; m += 2)
                {
                    GameObject edgeObj = new GameObject("Edge_" + lane.id + (m < 0 ? "_L" : "_R"));
                    edgeObj.transform.parent = laneObj.transform;
                    LineRenderer elr = edgeObj.AddComponent<LineRenderer>();
                    elr.positionCount = lane.shape.Length;
                    elr.startWidth = 0.1f;
                    elr.endWidth = 0.1f;
                    elr.material = solidMarkingMat;
                    elr.useWorldSpace = false;
                    
                    for (int i = 0; i < lane.shape.Length; i++)
                    {
                        Vector3 centerPos = new Vector3(lane.shape[i].x, 0.05f, lane.shape[i].y);
                        Vector3 right = Vector3.right;
                        if (i < lane.shape.Length - 1) {
                            Vector3 fwd = new Vector3(lane.shape[i+1].x - lane.shape[i].x, 0, lane.shape[i+1].y - lane.shape[i].y).normalized;
                            right = Vector3.Cross(Vector3.up, fwd).normalized;
                        } else if (i > 0) {
                            Vector3 fwd = new Vector3(lane.shape[i].x - lane.shape[i-1].x, 0, lane.shape[i].y - lane.shape[i-1].y).normalized;
                            right = Vector3.Cross(Vector3.up, fwd).normalized;
                        }
                        // Offset by half width minus a small margin so it sits on the road
                        Vector3 pos = centerPos + (right * ((width / 2f - 0.15f) * m));
                        elr.SetPosition(i, pos);
                    }
                }
            }
        }
        
        // Render Junctions and TLS
        GameObject junctionsParent = GameObject.Find("Environment/Intersections");
        if (junctionsParent == null) junctionsParent = new GameObject("SUMO_Junctions");
        
        GameObject tlsParent = GameObject.Find("MangaluruDigitalTwin/Traffic/TrafficSignals");
        if (tlsParent == null) tlsParent = GameObject.Find("Traffic/TrafficSignals");
        if (tlsParent == null) tlsParent = GameObject.Find("TrafficSignals");
        if (tlsParent == null) tlsParent = new GameObject("SUMO_TLS");
        if (networkData.junctions != null)
        {
            foreach (JunctionData junc in networkData.junctions)
            {
                if (junc.shape != null && junc.shape.Length >= 3)
                {
                    GameObject juncObj = new GameObject("Junction_" + junc.id);
                    juncObj.transform.parent = junctionsParent.transform;
                    juncObj.isStatic = true;
                    
                    MeshFilter mf = juncObj.AddComponent<MeshFilter>();
                    MeshRenderer mr = juncObj.AddComponent<MeshRenderer>();
                    mr.material = mat;
                    
                    mf.mesh = GenerateJunctionMesh(junc.shape);
                }
            }
        }
        
        if (networkData.traffic_lights != null)
        {
            // Build a quick lookup for lane geometry to accurately place signals at lane ends
            Dictionary<string, LaneData> laneDict = new Dictionary<string, LaneData>();
            if (networkData.edges != null)
            {
                foreach (EdgeData edge in networkData.edges)
                {
                    if (edge.lanes == null) continue;
                    foreach (LaneData lane in edge.lanes)
                    {
                        laneDict[lane.id] = lane;
                    }
                }
            }

            GameObject prefab = Resources.Load<GameObject>("TrafficSignalPrefab");
            if (prefab == null)
            {
                Debug.LogError("TrafficSignalPrefab could not be loaded from Resources!");
            }
            else
            {
                // Prevent duplicate TLS objects from accumulating
                List<GameObject> toDestroy = new List<GameObject>();
                foreach (Transform child in tlsParent.transform)
                {
                    toDestroy.Add(child.gameObject);
                }
                foreach (GameObject go in toDestroy)
                {
                    DestroyImmediate(go);
                }

                foreach (TlsData tls in networkData.traffic_lights)
                {
                    GameObject tlsRoot = new GameObject("TLS_" + tls.id);
                    tlsRoot.transform.parent = tlsParent.transform;
                    tlsRoot.transform.localPosition = new Vector3(tls.x, 0f, tls.y);
                    
                    allTlsRoots[tls.id] = tlsRoot;
                    tlsToIncomingEdges[tls.id] = new HashSet<string>();
                    
                    HashSet<string> processedEdges = new HashSet<string>();

                    if (tls.controlled_links != null)
                    {
                        foreach (TlsLinkData link in tls.controlled_links)
                        {
                            if (string.IsNullOrEmpty(link.from_lane))
                                continue;
                                
                            // Authoritative SUMO rule: internal edges always start with ':'
                            if (link.from_lane.StartsWith(":"))
                                continue;
                                
                            // Extract edge ID from lane ID (e.g. "1538932912#4_1" -> "1538932912#4")
                            int lastUnderscore = link.from_lane.LastIndexOf('_');
                            string fromEdge = lastUnderscore > 0 ? link.from_lane.Substring(0, lastUnderscore) : link.from_lane;

                            tlsToIncomingEdges[tls.id].Add(fromEdge);

                            if (processedEdges.Contains(fromEdge))
                                continue;

                            processedEdges.Add(fromEdge);
                            
                            if (laneDict.TryGetValue(link.from_lane, out LaneData laneData))
                            {
                                if (laneData.shape == null || laneData.shape.Length < 2) continue;
                                
                                if (!edgeShapes.ContainsKey(fromEdge)) {
                                    Vector3[] pts = new Vector3[laneData.shape.Length];
                                    for(int i=0; i<laneData.shape.Length; i++) pts[i] = new Vector3(laneData.shape[i].x, 0, laneData.shape[i].y);
                                    edgeShapes[fromEdge] = pts;
                                }
                                
                                Point2D pPrev = laneData.shape[laneData.shape.Length - 2];
                                Point2D pLast = laneData.shape[laneData.shape.Length - 1];
                                
                                Vector3 posPrev = new Vector3(pPrev.x, 0, pPrev.y);
                                Vector3 posLast = new Vector3(pLast.x, 0, pLast.y);
                                
                                Vector3 dir = (posLast - posPrev).normalized;
                                if (dir == Vector3.zero) continue;
                                
                                // ASSUMPTION: India relies on left-hand traffic, so we place the signal on the LEFT side of the approach lane.
                                // In Unity's left-handed coordinate system, Cross(up, dir) points right. We negate it to get left.
                                // The offset is configurable here. 2.5 meters pushes it outside the standard lane width.
                                float leftRoadsideOffset = 2.5f; 
                                Vector3 leftDir = -Vector3.Cross(Vector3.up, dir).normalized;
                                
                                Vector3 signalPos = posLast + (leftDir * leftRoadsideOffset);
                                
                                // Create prominent stop line across the approach lane
                                GameObject stopLineObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
                                stopLineObj.name = "StopLine_" + fromEdge;
                                stopLineObj.transform.parent = tlsRoot.transform;
                                Object.Destroy(stopLineObj.GetComponent<Collider>());
                                
                                float laneWidth = laneData.width > 0 ? laneData.width : defaultLineWidth;
                                stopLineObj.transform.localPosition = posLast + (Vector3.up * 0.06f) - new Vector3(tls.x, 0f, tls.y);
                                stopLineObj.transform.localRotation = Quaternion.Euler(90f, Quaternion.LookRotation(dir, Vector3.up).eulerAngles.y, 0f);
                                stopLineObj.transform.localScale = new Vector3(laneWidth, 0.5f, 1f);
                                
                                Renderer stopRend = stopLineObj.GetComponent<Renderer>();
                                if (stopRend != null) stopRend.sharedMaterial = solidMarkingMat;

                                GameObject signalObj = Instantiate(prefab, tlsRoot.transform);
                                signalObj.name = "Signal_" + fromEdge;
                                
                                // Subtract tlsRoot's local position so the signal positions correctly relative to its parent
                                signalObj.transform.localPosition = signalPos - new Vector3(tls.x, 0f, tls.y);
                                
                                // The signal face must point towards approaching traffic (-dir)
                                signalObj.transform.localRotation = Quaternion.LookRotation(-dir, Vector3.up);
                            }
                        }
                    }
                }
            }
        }
        
        // Render Buildings
        GameObject buildingsParent = GameObject.Find("Environment/Buildings");
        if (buildingsParent == null) buildingsParent = new GameObject("SUMO_Buildings");
        if (networkData.buildings != null)
        {
            // Load selected 3D building model prefabs
            GameObject[] resPrefabs = new GameObject[]
            {
                Resources.Load<GameObject>("Buildings/Bldg_House01"),
                Resources.Load<GameObject>("Buildings/Bldg_House02"),
                Resources.Load<GameObject>("Buildings/Bldg_House05"),
                Resources.Load<GameObject>("Buildings/Bldg_House07"),
                Resources.Load<GameObject>("Buildings/Bldg_House11")
            };
            GameObject[] comPrefabs = new GameObject[]
            {
                Resources.Load<GameObject>("Buildings/Bldg_Commercial01"),
                Resources.Load<GameObject>("Buildings/Bldg_Commercial02"),
                Resources.Load<GameObject>("Buildings/Bldg_Commercial03"),
                Resources.Load<GameObject>("Buildings/Bldg_Office01"),
                Resources.Load<GameObject>("Buildings/Bldg_Office02")
            };

            // Filter out any null prefabs
            List<GameObject> validRes = new List<GameObject>();
            foreach (var p in resPrefabs) if (p != null) validRes.Add(p);

            List<GameObject> validCom = new List<GameObject>();
            foreach (var p in comPrefabs) if (p != null) validCom.Add(p);

            // Refined architectural materials for procedural fallback buildings
            Material[] fallbackMats = new Material[4];
            Color[] colors = { 
                new Color(0.82f, 0.80f, 0.76f), // Light sandstone
                new Color(0.72f, 0.70f, 0.66f), // Warm concrete
                new Color(0.68f, 0.72f, 0.75f), // Urban muted slate
                new Color(0.78f, 0.74f, 0.70f)  // Soft beige stucco
            };
            for (int i = 0; i < 4; i++) {
                fallbackMats[i] = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                fallbackMats[i].color = colors[i];
            }
            
            // Deterministic random state to prevent building jitter across runs
            Random.InitState(42);

            int modelPlacedCount = 0;
            int fallbackPlacedCount = 0;
            
            foreach (BuildingData bldg in networkData.buildings)
            {
                if (bldg.shape == null || bldg.shape.Length < 3) continue;
                
                // Calculate bounding box of the plot footprint
                float minX = float.MaxValue, minZ = float.MaxValue;
                float maxX = float.MinValue, maxZ = float.MinValue;
                
                foreach (Point2D p in bldg.shape)
                {
                    if (p.x < minX) minX = p.x;
                    if (p.x > maxX) maxX = p.x;
                    if (p.y < minZ) minZ = p.y;
                    if (p.y > maxZ) maxZ = p.y;
                }
                
                float sizeX = maxX - minX;
                float sizeZ = maxZ - minZ;
                float centerX = minX + sizeX / 2f;
                float centerZ = minZ + sizeZ / 2f;
                float aspect = Mathf.Max(sizeX, sizeZ) / Mathf.Max(0.1f, Mathf.Min(sizeX, sizeZ));
                float maxDim = Mathf.Max(sizeX, sizeZ);
                float minDim = Mathf.Min(sizeX, sizeZ);

                // Check suitability for placing a real 3D building model:
                // Plot must be standard proportions (10m to 46m dimensions, aspect ratio <= 2.2)
                bool fits3DModel = (minDim >= 10.0f && maxDim <= 46.0f && aspect <= 2.2f);
                bool modelPlaced = false;

                if (fits3DModel && (validRes.Count > 0 || validCom.Count > 0))
                {
                    GameObject chosenPrefab = null;
                    float nativeSpan = 16.0f; // Typical base span of models

                    if (maxDim < 26.0f && validRes.Count > 0)
                    {
                        chosenPrefab = validRes[Random.Range(0, validRes.Count)];
                        nativeSpan = 15.0f;
                    }
                    else if (validCom.Count > 0)
                    {
                        chosenPrefab = validCom[Random.Range(0, validCom.Count)];
                        nativeSpan = 24.0f;
                    }

                    if (chosenPrefab != null)
                    {
                        // Safe placement: Scale conservatively (80% of footprint) to guarantee zero road intrusion
                        float targetSpan = minDim * 0.80f;
                        float scale = Mathf.Clamp(targetSpan / nativeSpan, 0.45f, 1.4f);

                        // Align building to cardinal / plot orientation with 90-degree step
                        float rotY = (Random.Range(0, 4)) * 90f;

                        Vector3 bldgPos = new Vector3(centerX, 0f, centerZ);
                        GameObject bldgObj = Instantiate(chosenPrefab, buildingsParent.transform);
                        bldgObj.name = "BldgModel_" + bldg.id;
                        bldgObj.transform.localPosition = bldgPos;
                        bldgObj.transform.localRotation = Quaternion.Euler(0f, rotY, 0f);
                        bldgObj.transform.localScale = new Vector3(scale, scale, scale);
                        bldgObj.isStatic = true;

                        // Ensure no colliders on decorative buildings
                        foreach (Collider col in bldgObj.GetComponentsInChildren<Collider>())
                        {
                            Object.Destroy(col);
                        }

                        modelPlaced = true;
                        modelPlacedCount++;
                    }
                }

                if (!modelPlaced)
                {
                    // Procedural Fallback for irregular, tiny, or very large plots
                    float height = Mathf.Clamp((sizeX + sizeZ) * 0.4f, 6f, 32f);
                    
                    GameObject bObj = new GameObject("Building_Procedural_" + bldg.id);
                    bObj.transform.parent = buildingsParent.transform;
                    bObj.isStatic = true;
                    
                    MeshFilter mf = bObj.AddComponent<MeshFilter>();
                    MeshRenderer mr = bObj.AddComponent<MeshRenderer>();
                    mr.material = fallbackMats[Random.Range(0, 4)];
                    
                    mf.mesh = GenerateBuildingMesh(bldg.shape, height);
                    fallbackPlacedCount++;
                }
            }

            Debug.Log($"RoadVisualizer: Placed {modelPlacedCount} 3D architectural building models and {fallbackPlacedCount} clean procedural fallback buildings.");
        }
        // Render Road Labels
        GameObject labelsParent = GameObject.Find("Environment/RoadLabels");
        if (labelsParent == null) labelsParent = new GameObject("SUMO_RoadLabels");
        if (networkData.road_labels != null)
        {
            foreach (RoadLabelData label in networkData.road_labels)
            {
                GameObject signObj = new GameObject("Label_" + label.name.Replace(" ", ""));
                signObj.transform.parent = labelsParent.transform;
                // Place slightly above the road surface
                signObj.transform.localPosition = new Vector3(label.x, 2.0f, label.y);
                
                // Align text flat against the ground plane so overhead camera can read it easily
                signObj.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
                
                TextMesh tm = signObj.AddComponent<TextMesh>();
                tm.text = label.name;
                tm.characterSize = 0.5f;
                tm.fontSize = 64;
                tm.anchor = TextAnchor.MiddleCenter;
                tm.alignment = TextAlignment.Center;
                tm.color = Color.white;
                
                // Add a dark outline/shadow effect by duplicating
                GameObject shadowObj = new GameObject("Shadow");
                shadowObj.transform.parent = signObj.transform;
                shadowObj.transform.localPosition = new Vector3(0.5f, -0.5f, 0.1f);
                shadowObj.transform.localRotation = Quaternion.identity;
                
                TextMesh s_tm = shadowObj.AddComponent<TextMesh>();
                s_tm.text = label.name;
                s_tm.characterSize = 0.5f;
                s_tm.fontSize = 64;
                s_tm.anchor = TextAnchor.MiddleCenter;
                s_tm.alignment = TextAlignment.Center;
                s_tm.color = Color.black;
            }
        }
        
        // Log boundaries for debugging
        float roadMinX = float.MaxValue, roadMinZ = float.MaxValue;
        float roadMaxX = float.MinValue, roadMaxZ = float.MinValue;
        foreach (EdgeData edge in networkData.edges)
        {
            foreach (LaneData lane in edge.lanes)
            {
                if (lane.shape == null) continue;
                foreach (Point2D p in lane.shape)
                {
                    if (p.x < roadMinX) roadMinX = p.x;
                    if (p.x > roadMaxX) roadMaxX = p.x;
                    if (p.y < roadMinZ) roadMinZ = p.y;
                    if (p.y > roadMaxZ) roadMaxZ = p.y;
                }
            }
        }
        Debug.Log($"\n[ROAD DEBUG]\nminX={roadMinX}\nmaxX={roadMaxX}\nminZ={roadMinZ}\nmaxZ={roadMaxZ}\n");
        
        Debug.Log($"Successfully rendered {networkData.edges.Length} edges, {(networkData.junctions != null ? networkData.junctions.Length : 0)} junctions, and {(networkData.buildings != null ? networkData.buildings.Length : 0)} buildings.");
    }



    Mesh GenerateJunctionMesh(Point2D[] shape)
    {
        int numPoints = shape.Length;
        // Simple fan triangulation from centroid
        Vector3[] vertices = new Vector3[numPoints + 1];
        int[] triangles = new int[numPoints * 3];
        
        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            vertices[i] = new Vector3(shape[i].x, 0f, shape[i].y);
            centroid += vertices[i];
        }
        centroid /= numPoints;
        vertices[numPoints] = centroid; // Center vertex
        
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            triangles[i * 3] = numPoints; // center
            triangles[i * 3 + 1] = next;
            triangles[i * 3 + 2] = i; // Ensure correct winding (might need swap depending on shape order, usually SUMO is CCW/CW consistent)
            
            // To be safe and render both sides (since it's flat), we could just duplicate triangles, 
            // but typical SUMO polygons are ordered CCW or CW. If invisible, we'd adjust winding.
        }
        
        Mesh mesh = new Mesh();
        mesh.vertices = vertices;
        mesh.triangles = triangles;
        mesh.RecalculateNormals();
        return mesh;
    }

    Mesh GenerateBuildingMesh(Point2D[] shape, float height)
    {
        int numPoints = shape.Length;
        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();

        // Roof centroid
        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            centroid += new Vector3(shape[i].x, height, shape[i].y);
        }
        centroid /= numPoints;

        int roofStartIndex = verts.Count;
        verts.Add(centroid);
        for (int i = 0; i < numPoints; i++)
        {
            verts.Add(new Vector3(shape[i].x, height, shape[i].y));
        }

        // Roof Triangles
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            tris.Add(roofStartIndex);
            tris.Add(roofStartIndex + 1 + i);
            tris.Add(roofStartIndex + 1 + next);
        }

        // Walls
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            Vector3 bl = new Vector3(shape[i].x, 0, shape[i].y);
            Vector3 br = new Vector3(shape[next].x, 0, shape[next].y);
            Vector3 tl = new Vector3(shape[i].x, height, shape[i].y);
            Vector3 tr = new Vector3(shape[next].x, height, shape[next].y);

            int wStart = verts.Count;
            verts.Add(bl);
            verts.Add(br);
            verts.Add(tl);
            verts.Add(tr);

            tris.Add(wStart);
            tris.Add(wStart + 2);
            tris.Add(wStart + 1);

            tris.Add(wStart + 1);
            tris.Add(wStart + 2);
            tris.Add(wStart + 3);
        }

        Mesh mesh = new Mesh();
        mesh.vertices = verts.ToArray();
        mesh.triangles = tris.ToArray();
        mesh.RecalculateNormals();
        return mesh;
    }

    Mesh GenerateLaneMesh(Point2D[] shape, float width)
    {
        int numPoints = shape.Length;
        Vector3[] vertices = new Vector3[numPoints * 2];
        int[] triangles = new int[(numPoints - 1) * 6];
        Vector2[] uvs = new Vector2[numPoints * 2];

        float halfWidth = width / 2f;

        // Convert SUMO points to Unity points
        Vector3[] pathPoints = new Vector3[numPoints];
        for (int i = 0; i < numPoints; i++)
        {
            pathPoints[i] = new Vector3(shape[i].x, 0f, shape[i].y);
        }

        for (int i = 0; i < numPoints; i++)
        {
            Vector3 forward = Vector3.forward;

            if (i < numPoints - 1)
            {
                forward = (pathPoints[i + 1] - pathPoints[i]).normalized;
            }
            else if (i > 0)
            {
                forward = (pathPoints[i] - pathPoints[i - 1]).normalized;
            }

            // Calculate right vector
            Vector3 right = Vector3.Cross(Vector3.up, forward).normalized;

            // Generate left and right vertices
            vertices[i * 2] = pathPoints[i] - right * halfWidth;     // Left vertex
            vertices[i * 2 + 1] = pathPoints[i] + right * halfWidth; // Right vertex

            // Basic UV mapping
            float v = (float)i / (numPoints - 1);
            uvs[i * 2] = new Vector2(0, v);
            uvs[i * 2 + 1] = new Vector2(1, v);
        }

        for (int i = 0; i < numPoints - 1; i++)
        {
            int vIndex = i * 2;
            int tIndex = i * 6;

            // First triangle (Left, Next Left, Right)
            triangles[tIndex] = vIndex;
            triangles[tIndex + 1] = vIndex + 2;
            triangles[tIndex + 2] = vIndex + 1;

            // Second triangle (Right, Next Left, Next Right)
            triangles[tIndex + 3] = vIndex + 1;
            triangles[tIndex + 4] = vIndex + 2;
            triangles[tIndex + 5] = vIndex + 3;
        }

        Mesh mesh = new Mesh();
        mesh.vertices = vertices;
        mesh.triangles = triangles;
        mesh.uv = uvs;
        mesh.RecalculateNormals();
        mesh.RecalculateBounds();

        return mesh;
    }
}
