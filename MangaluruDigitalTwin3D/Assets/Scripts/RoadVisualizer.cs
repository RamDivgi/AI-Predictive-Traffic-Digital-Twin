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
public class ConflictData {
    public string type;
    public bool hits_road;
    public bool hits_junction;
    public float overlap_area_m2;
    public float clearance_m;
}

[System.Serializable]
public class BuildingData {
    public string id;
    public string name;
    public string building_type;
    public Point2D[] shape;
    public bool is_infill;
    public float facing;
    public string source;
    public ConflictData conflict;
    public bool is_hospital_site;
}

[System.Serializable]
public class ParkData {
    public string id;
    public string type;
    public Point2D[] shape;
}

[System.Serializable]
public class HospitalData {
    public string id;
    public string name;
    public float x;
    public float y;
    public string matched_building_id;
    public float footprint_width;
    public float footprint_depth;
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
    public ParkData[] parks;
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
    
    private struct RoadLaneSegment {
        public Vector2 p1;
        public Vector2 p2;
        public float width;
    }

    private Dictionary<string, GameObject> allTlsRoots = new Dictionary<string, GameObject>();
    private Dictionary<string, HashSet<string>> tlsToIncomingEdges = new Dictionary<string, HashSet<string>>();
    private Dictionary<string, Vector3[]> edgeShapes = new Dictionary<string, Vector3[]>();

    void Start()
    {
        if (hasRendered) return;
        hasRendered = true;
        LoadAndRenderRoads();
    }

    public void ForceRegenerate()
    {
        hasRendered = false;
        LoadAndRenderRoads();
    }

    private void ClearChildren(GameObject parent)
    {
        if (parent == null) return;
        for (int i = parent.transform.childCount - 1; i >= 0; i--)
        {
            DestroyImmediate(parent.transform.GetChild(i).gameObject);
        }
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
        ClearChildren(roadsParent);

        Material mat = roadMaterial;
        if (mat == null)
        {
            mat = Resources.Load<Material>("Asphalt");
        }
        if (mat == null)
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) shader = Shader.Find("Standard");
            mat = new Material(shader);
            Color asphaltColor = new Color(0.18f, 0.18f, 0.20f, 1.0f);
            mat.color = asphaltColor;
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", asphaltColor);
            if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", 0.15f);
        }
        
        // Create an urban ground plane anchored below the road network (-0.35m) to prevent Z-fighting
        GameObject ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "CityGround";
        ground.transform.parent = roadsParent.transform;
        ground.transform.localPosition = new Vector3(1600f, -0.35f, 1600f); // Center of Mangaluru coords
        ground.transform.localScale = new Vector3(1000f, 1f, 1000f); // 10km x 10km
        Material groundMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        Color terrainColor = new Color(0.18f, 0.20f, 0.17f, 1.0f); // Soft natural urban terrain base
        groundMat.color = terrainColor;
        if (groundMat.HasProperty("_BaseColor")) groundMat.SetColor("_BaseColor", terrainColor);
        if (groundMat.HasProperty("_Smoothness")) groundMat.SetFloat("_Smoothness", 0.05f);
        ground.GetComponent<Renderer>().material = groundMat;
        Destroy(ground.GetComponent<Collider>()); // Don't need physics for ground
        
        Shader litShader = Shader.Find("Universal Render Pipeline/Lit");
        if (litShader == null) litShader = Shader.Find("Standard");

        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");

        Material markingMat = new Material(unlitShader);
        markingMat.color = Color.white;
        
        Material solidMarkingMat = new Material(unlitShader);
        solidMarkingMat.color = Color.white;

        // Pale concrete sidewalk material
        Material sidewalkMat = new Material(litShader);
        Color concreteColor = new Color(0.72f, 0.70f, 0.67f, 1.0f);
        sidewalkMat.color = concreteColor;
        if (sidewalkMat.HasProperty("_BaseColor")) sidewalkMat.SetColor("_BaseColor", concreteColor);
        if (sidewalkMat.HasProperty("_Smoothness")) sidewalkMat.SetFloat("_Smoothness", 0.08f);

        // Streetlight pole metallic material
        Material poleMat = new Material(litShader);
        Color poleColor = new Color(0.22f, 0.24f, 0.26f, 1.0f);
        poleMat.color = poleColor;
        if (poleMat.HasProperty("_BaseColor")) poleMat.SetColor("_BaseColor", poleColor);

        // Warm emissive luminaire head material
        Material luminaireMat = new Material(unlitShader);
        Color lumColor = new Color(1.0f, 0.95f, 0.82f, 1.0f);
        luminaireMat.color = lumColor;
        if (luminaireMat.HasProperty("_BaseColor")) luminaireMat.SetColor("_BaseColor", lumColor);

        // High-contrast pedestrian zebra crossing material
        Material zebraMat = new Material(unlitShader);
        Texture2D zebraTex = new Texture2D(32, 128);
        zebraTex.filterMode = FilterMode.Bilinear;
        zebraTex.wrapMode = TextureWrapMode.Repeat;
        for (int y = 0; y < 128; y++) {
            bool isWhite = (y % 16) < 10;
            Color c = isWhite ? Color.white : new Color(0.18f, 0.18f, 0.20f, 0.95f);
            for (int x = 0; x < 32; x++) {
                zebraTex.SetPixel(x, y, c);
            }
        }
        zebraTex.Apply();
        zebraMat.mainTexture = zebraTex;
        
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
        
        // Render Sidewalks, Raised Curbs & Streetlights along outer road corridors
        GameObject sidewalksParent = GameObject.Find("Environment/Sidewalks");
        if (sidewalksParent == null) sidewalksParent = new GameObject("SUMO_Sidewalks");
        sidewalksParent.transform.parent = roadsParent.transform;

        GameObject streetlightsParent = GameObject.Find("Environment/Streetlights");
        if (streetlightsParent == null) streetlightsParent = new GameObject("SUMO_Streetlights");
        streetlightsParent.transform.parent = roadsParent.transform;

        if (networkData.edges != null)
        {
            foreach (EdgeData edge in networkData.edges)
            {
                if (edge.lanes == null || edge.lanes.Length == 0) continue;
                LaneData outerLane = edge.lanes[0];
                if (outerLane.shape == null || outerLane.shape.Length < 2) continue;

                float laneW = outerLane.width > 0 ? outerLane.width : defaultLineWidth;

                // Generate raised concrete sidewalk ribbon along outer road edge
                GameObject swObj = new GameObject("Sidewalk_" + edge.id);
                swObj.transform.parent = sidewalksParent.transform;
                swObj.isStatic = true;
                MeshFilter swMf = swObj.AddComponent<MeshFilter>();
                MeshRenderer swMr = swObj.AddComponent<MeshRenderer>();
                swMr.sharedMaterial = sidewalkMat;
                swMf.mesh = GenerateSidewalkMesh(outerLane.shape, laneW, 1.5f, 0.13f);

                // Calculate total edge length for streetlight placement
                float edgeDist = 0f;
                for (int i = 0; i < outerLane.shape.Length - 1; i++)
                {
                    edgeDist += Vector2.Distance(new Vector2(outerLane.shape[i].x, outerLane.shape[i].y),
                                                 new Vector2(outerLane.shape[i + 1].x, outerLane.shape[i + 1].y));
                }

                // Place streetlights at ~35m intervals along edges of sufficient length
                if (edgeDist >= 28.0f)
                {
                    int lightCount = Mathf.FloorToInt(edgeDist / 35.0f);
                    for (int k = 1; k <= lightCount; k++)
                    {
                        float targetDist = k * (edgeDist / (lightCount + 1));
                        Vector3 samplePos = SamplePointAlongShape3D(outerLane.shape, targetDist, out Vector3 forwardDir);
                        Vector3 right = Vector3.Cross(Vector3.up, forwardDir).normalized;
                        Vector3 left = -right;

                        // Position on outer sidewalk verge
                        Vector3 lightPos = samplePos + left * (laneW * 0.5f + 1.2f) + Vector3.up * 0.13f;
                        CreateStreetlight(streetlightsParent.transform, lightPos, right, poleMat, luminaireMat);
                    }
                }
            }
        }

        // Render Junctions and TLS
        GameObject junctionsParent = GameObject.Find("Environment/Intersections");
        if (junctionsParent == null) junctionsParent = new GameObject("SUMO_Junctions");
        ClearChildren(junctionsParent);
        
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

                                // Add pedestrian zebra crossing 2.2m upstream from stop line
                                GameObject zebraObj = GameObject.CreatePrimitive(PrimitiveType.Quad);
                                zebraObj.name = "ZebraCrossing_" + fromEdge;
                                zebraObj.transform.parent = tlsRoot.transform;
                                Object.Destroy(zebraObj.GetComponent<Collider>());
                                
                                Vector3 zebraPos = posLast - (dir * 2.2f) + (Vector3.up * 0.055f) - new Vector3(tls.x, 0f, tls.y);
                                zebraObj.transform.localPosition = zebraPos;
                                zebraObj.transform.localRotation = Quaternion.Euler(90f, Quaternion.LookRotation(dir, Vector3.up).eulerAngles.y, 0f);
                                zebraObj.transform.localScale = new Vector3(laneWidth, 2.6f, 1f);
                                
                                Renderer zebraRend = zebraObj.GetComponent<Renderer>();
                                if (zebraRend != null) zebraRend.sharedMaterial = zebraMat;

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
        ClearChildren(buildingsParent);
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
                new Color(0.58f, 0.55f, 0.50f), // Warm sandstone
                new Color(0.50f, 0.50f, 0.48f), // Concrete
                new Color(0.46f, 0.50f, 0.54f), // Urban muted slate
                new Color(0.54f, 0.52f, 0.48f)  // Warm beige stucco
            };
            for (int i = 0; i < 4; i++) {
                fallbackMats[i] = new Material(litShader);
                fallbackMats[i].color = colors[i];
                if (fallbackMats[i].HasProperty("_BaseColor")) fallbackMats[i].SetColor("_BaseColor", colors[i]);
                if (fallbackMats[i].HasProperty("_Smoothness")) fallbackMats[i].SetFloat("_Smoothness", 0.10f);
            }

            // Authentic Mangaluru Terracotta Tile Red Roof Material
            Material terracottaRoofMat = new Material(litShader);
            Color terracottaCol = new Color(0.72f, 0.28f, 0.16f, 1.0f);
            terracottaRoofMat.color = terracottaCol;
            if (terracottaRoofMat.HasProperty("_BaseColor")) terracottaRoofMat.SetColor("_BaseColor", terracottaCol);
            if (terracottaRoofMat.HasProperty("_Smoothness")) terracottaRoofMat.SetFloat("_Smoothness", 0.20f);

            // Commercial Storefront Facade & Frame Material
            Material storefrontMat = new Material(litShader);
            Color storefrontCol = new Color(0.14f, 0.16f, 0.18f, 1.0f);
            storefrontMat.color = storefrontCol;
            if (storefrontMat.HasProperty("_BaseColor")) storefrontMat.SetColor("_BaseColor", storefrontCol);
            if (storefrontMat.HasProperty("_Smoothness")) storefrontMat.SetFloat("_Smoothness", 0.40f);

            // Dressed Granite Plinth Foundation Material
            Material plinthMat = new Material(litShader);
            Color plinthCol = new Color(0.26f, 0.26f, 0.25f, 1.0f);
            plinthMat.color = plinthCol;
            if (plinthMat.HasProperty("_BaseColor")) plinthMat.SetColor("_BaseColor", plinthCol);
            if (plinthMat.HasProperty("_Smoothness")) plinthMat.SetFloat("_Smoothness", 0.12f);

            // Sintex Dark Navy Overhead Water Storage Tank Material
            Material waterTankMat = new Material(litShader);
            Color tankCol = new Color(0.11f, 0.21f, 0.36f, 1.0f);
            waterTankMat.color = tankCol;
            if (waterTankMat.HasProperty("_BaseColor")) waterTankMat.SetColor("_BaseColor", tankCol);
            if (waterTankMat.HasProperty("_Smoothness")) waterTankMat.SetFloat("_Smoothness", 0.25f);

            // Concrete Parapet Coping Material
            Material concreteCopingMat = new Material(litShader);
            Color copingCol = new Color(0.64f, 0.63f, 0.60f, 1.0f);
            concreteCopingMat.color = copingCol;
            if (concreteCopingMat.HasProperty("_BaseColor")) concreteCopingMat.SetColor("_BaseColor", copingCol);
            if (concreteCopingMat.HasProperty("_Smoothness")) concreteCopingMat.SetFloat("_Smoothness", 0.08f);

            // Frontage Compound Boundary Wall Material
            // Warning Red Material for Documented Source Conflicts
            Material warningRedMat = new Material(litShader);
            Color warningRedCol = new Color(0.92f, 0.20f, 0.20f, 1.0f);
            warningRedMat.color = warningRedCol;
            if (warningRedMat.HasProperty("_BaseColor")) warningRedMat.SetColor("_BaseColor", warningRedCol);
            if (warningRedMat.HasProperty("_Smoothness")) warningRedMat.SetFloat("_Smoothness", 0.30f);

            // Contrasting Cyan Material for Conflicting Road Highlight Regions
            Material cyanHighlightMat = new Material(unlitShader);
            Color cyanHighlightCol = new Color(0.0f, 0.88f, 0.98f, 0.75f);
            cyanHighlightMat.color = cyanHighlightCol;
            if (cyanHighlightMat.HasProperty("_BaseColor")) cyanHighlightMat.SetColor("_BaseColor", cyanHighlightCol);

            // Frontage Compound Boundary Wall Material
            Material compoundWallMat = new Material(litShader);
            Color compoundCol = new Color(0.68f, 0.66f, 0.63f, 1.0f);
            compoundWallMat.color = compoundCol;
            if (compoundWallMat.HasProperty("_BaseColor")) compoundWallMat.SetColor("_BaseColor", compoundCol);
            if (compoundWallMat.HasProperty("_Smoothness")) compoundWallMat.SetFloat("_Smoothness", 0.10f);
            
            // Deterministic random state to prevent building jitter across runs
            Random.InitState(42);

            // Pre-collect all road segments for frontage alignment and clearance checks
            List<RoadLaneSegment> roadSegments = new List<RoadLaneSegment>();
            if (networkData.edges != null)
            {
                foreach (EdgeData edge in networkData.edges)
                {
                    if (edge.lanes == null) continue;
                    foreach (LaneData lane in edge.lanes)
                    {
                        if (lane.shape == null || lane.shape.Length < 2) continue;
                        float w = lane.width > 0 ? lane.width : defaultLineWidth;
                        for (int i = 0; i < lane.shape.Length - 1; i++)
                        {
                            roadSegments.Add(new RoadLaneSegment
                            {
                                p1 = new Vector2(lane.shape[i].x, lane.shape[i].y),
                                p2 = new Vector2(lane.shape[i+1].x, lane.shape[i+1].y),
                                width = w
                            });
                        }
                    }
                }
            }

            // Pre-collect junction polygons for full intersection clearance validation
            List<Vector2[]> junctionPolys = new List<Vector2[]>();
            if (networkData.junctions != null)
            {
                foreach (var junc in networkData.junctions)
                {
                    if (junc.shape != null && junc.shape.Length >= 3)
                    {
                        Vector2[] pts = new Vector2[junc.shape.Length];
                        for (int i = 0; i < junc.shape.Length; i++)
                        {
                            pts[i] = new Vector2(junc.shape[i].x, junc.shape[i].y);
                        }
                        junctionPolys.Add(pts);
                    }
                }
            }

            // Exact prefab dimensions measured from Unity mesh filters (scratch/prefab_bounds.json)
            Dictionary<string, Vector4> prefabBoundsDict = new Dictionary<string, Vector4>
            {
                { "Bldg_House01", new Vector4(-6.60f, 6.60f, -9.28f, 7.93f) },
                { "Bldg_House02", new Vector4(-6.50f, 6.50f, -9.00f, 9.15f) },
                { "Bldg_House05", new Vector4(-8.44f, 8.60f, -8.46f, 9.24f) },
                { "Bldg_House07", new Vector4(-6.75f, 6.75f, -9.00f, 7.10f) },
                { "Bldg_House11", new Vector4(-6.75f, 6.75f, -9.00f, 7.10f) },
                { "Bldg_Commercial01", new Vector4(-7.50f, 7.50f, -8.50f, 8.50f) },
                { "Bldg_Commercial02", new Vector4(-13.75f, 12.50f, -12.75f, 13.77f) },
                { "Bldg_Commercial03", new Vector4(-18.50f, 18.50f, -8.75f, 8.75f) },
                { "Bldg_Office01", new Vector4(-6.35f, 6.35f, -10.80f, 12.25f) },
                { "Bldg_Office02", new Vector4(-19.00f, 19.00f, -10.50f, 10.50f) }
            };

            int modelPlacedCount = 0;
            int fallbackPlacedCount = 0;
            int conflictCount = 0;
            
            foreach (BuildingData bldg in networkData.buildings)
            {
                if (bldg.shape == null || bldg.shape.Length < 3) continue;
                
                // Calculate centroid from polygon footprint
                float sumX = 0f, sumZ = 0f;
                float minX = float.MaxValue, minZ = float.MaxValue;
                float maxX = float.MinValue, maxZ = float.MinValue;
                
                foreach (Point2D p in bldg.shape)
                {
                    sumX += p.x;
                    sumZ += p.y;
                    if (p.x < minX) minX = p.x;
                    if (p.x > maxX) maxX = p.x;
                    if (p.y < minZ) minZ = p.y;
                    if (p.y > maxZ) maxZ = p.y;
                }
                
                int ptCount = bldg.shape.Length;
                float centerX = sumX / ptCount;
                float centerZ = sumZ / ptCount;
                Vector2 centroid = new Vector2(centerX, centerZ);

                float sizeX = maxX - minX;
                float sizeZ = maxZ - minZ;
                float minDim = Mathf.Min(sizeX, sizeZ);
                float maxDim = Mathf.Max(sizeX, sizeZ);
                float aspect = maxDim / Mathf.Max(0.1f, minDim);

                // Find nearest road frontage segment
                float minRoadEdgeDist = float.MaxValue;
                Vector2 nearestRoadProj = Vector2.zero;
                foreach (var seg in roadSegments)
                {
                    Vector2 d = seg.p2 - seg.p1;
                    float l2 = d.sqrMagnitude;
                    float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(centroid - seg.p1, d) / l2) : 0f;
                    Vector2 proj = seg.p1 + t * d;
                    float dist = Vector2.Distance(centroid, proj);
                    float edgeDist = dist - (seg.width * 0.5f);
                    if (edgeDist < minRoadEdgeDist)
                    {
                        minRoadEdgeDist = edgeDist;
                        nearestRoadProj = proj;
                    }
                }

                // Skip building if it is occupied by a hospital landmark (HospitalVisualizer renders it)
                if (bldg.is_hospital_site)
                {
                    continue;
                }

                // Check clearance to hospital locations
                bool nearHospital = false;
                if (networkData.hospitals != null)
                {
                    foreach (var hosp in networkData.hospitals)
                    {
                        if (Vector2.Distance(centroid, new Vector2(hosp.x, hosp.y)) < 26.0f)
                        {
                            nearHospital = true;
                            break;
                        }
                    }
                }
                if (nearHospital) continue;

                bool isConflict = (bldg.conflict != null && !string.IsNullOrEmpty(bldg.conflict.type));
                if (isConflict) conflictCount++;

                // 3D Model candidate suitability:
                // Only non-conflicts with good dimensions
                bool fits3DModel = (!isConflict && minDim >= 10.0f && maxDim <= 45.0f && aspect <= 2.2f);
                bool modelPlaced = false;

                if (fits3DModel && (validRes.Count > 0 || validCom.Count > 0))
                {
                    GameObject chosenPrefab = null;
                    bool preferCom = (bldg.building_type == "commercial" || bldg.building_type == "office" || bldg.building_type == "retail");
                    bool preferRes = (bldg.building_type == "house" || bldg.building_type == "residential");

                    if (preferCom && validCom.Count > 0)
                    {
                        chosenPrefab = validCom[Random.Range(0, validCom.Count)];
                    }
                    else if (preferRes && validRes.Count > 0)
                    {
                        chosenPrefab = validRes[Random.Range(0, validRes.Count)];
                    }
                    else if (maxDim < 26.0f && validRes.Count > 0)
                    {
                        chosenPrefab = validRes[Random.Range(0, validRes.Count)];
                    }
                    else if (validCom.Count > 0)
                    {
                        chosenPrefab = validCom[Random.Range(0, validCom.Count)];
                    }

                    if (chosenPrefab != null)
                    {
                        Vector4 pBounds;
                        if (!prefabBoundsDict.TryGetValue(chosenPrefab.name, out pBounds))
                        {
                            pBounds = new Vector4(-7.5f, 7.5f, -7.5f, 7.5f);
                        }
                        float pSizeX = pBounds.y - pBounds.x;
                        float pSizeZ = pBounds.w - pBounds.z;

                        // Scale to strictly fit within the parcel footprint
                        float scaleW = sizeX / Mathf.Max(1.0f, pSizeX);
                        float scaleD = sizeZ / Mathf.Max(1.0f, pSizeZ);
                        float scale = Mathf.Clamp(Mathf.Min(scaleW, scaleD) * 0.90f, 0.55f, 1.15f);

                        // Facing angle
                        float faceAngle = 0f;
                        if (bldg.is_infill && Mathf.Abs(bldg.facing) > 0.01f)
                        {
                            faceAngle = bldg.facing;
                        }
                        else
                        {
                            Vector2 toRoad = nearestRoadProj - centroid;
                            faceAngle = Mathf.Atan2(toRoad.x, toRoad.y) * Mathf.Rad2Deg;
                        }

                        // Compute rotated 4 corners of prefab in Unity coordinates
                        float rad = faceAngle * Mathf.Deg2Rad;
                        float cosA = Mathf.Cos(rad);
                        float sinA = Mathf.Sin(rad);

                        float cMinX = pBounds.x * scale;
                        float cMaxX = pBounds.y * scale;
                        float cMinZ = pBounds.z * scale;
                        float cMaxZ = pBounds.w * scale;

                        Vector2[] testCorners = new Vector2[4]
                        {
                            new Vector2(centerX + (cMinX * cosA + cMinZ * sinA), centerZ + (-cMinX * sinA + cMinZ * cosA)),
                            new Vector2(centerX + (cMaxX * cosA + cMinZ * sinA), centerZ + (-cMaxX * sinA + cMinZ * cosA)),
                            new Vector2(centerX + (cMaxX * cosA + cMaxZ * sinA), centerZ + (-cMaxX * sinA + cMaxZ * cosA)),
                            new Vector2(centerX + (cMinX * cosA + cMaxZ * sinA), centerZ + (-cMinX * sinA + cMaxZ * cosA))
                        };

                        // Verify that ALL corners maintain >= 2.0m clearance to roads & junctions
                        bool prefabClear = true;
                        foreach (var c in testCorners)
                        {
                            foreach (var seg in roadSegments)
                            {
                                Vector2 d = seg.p2 - seg.p1;
                                float l2 = d.sqrMagnitude;
                                float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(c - seg.p1, d) / l2) : 0f;
                                float dist = Vector2.Distance(c, seg.p1 + t * d) - (seg.width * 0.5f);
                                if (dist < 1.8f) { prefabClear = false; break; }
                            }
                            if (!prefabClear) break;

                            foreach (var jPoly in junctionPolys)
                            {
                                if (PointInPolygon(c, jPoly)) { prefabClear = false; break; }
                                for (int k = 0; k < jPoly.Length; k++)
                                {
                                    Vector2 jp1 = jPoly[k];
                                    Vector2 jp2 = jPoly[(k + 1) % jPoly.Length];
                                    Vector2 jd = jp2 - jp1;
                                    float jl2 = jd.sqrMagnitude;
                                    float jt = (jl2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(c - jp1, jd) / jl2) : 0f;
                                    float jDist = Vector2.Distance(c, jp1 + jt * jd);
                                    if (jDist < 1.8f) { prefabClear = false; break; }
                                }
                                if (!prefabClear) break;
                            }
                            if (!prefabClear) break;
                        }

                        if (prefabClear)
                        {
                            Vector3 bldgPos = new Vector3(centerX, 0f, centerZ);
                            GameObject bldgObj = Instantiate(chosenPrefab, buildingsParent.transform);
                            bldgObj.name = "BldgModel_" + bldg.id;
                            bldgObj.transform.localPosition = bldgPos;
                            bldgObj.transform.localRotation = Quaternion.Euler(0f, faceAngle, 0f);
                            bldgObj.transform.localScale = new Vector3(scale, scale, scale);
                            bldgObj.isStatic = true;

                            foreach (Collider col in bldgObj.GetComponentsInChildren<Collider>())
                            {
                                Object.Destroy(col);
                            }

                            modelPlaced = true;
                            modelPlacedCount++;
                        }
                    }
                }

                if (!modelPlaced)
                {
                    int bldgHash = Mathf.Abs(bldg.id.GetHashCode());
                    int typology = bldgHash % 3;

                    if (bldg.building_type == "commercial" || bldg.building_type == "office" || bldg.building_type == "retail")
                    {
                        typology = 1;
                    }
                    else if (bldg.building_type == "apartments")
                    {
                        typology = 2;
                    }
                    else if (bldg.building_type == "house" || bldg.building_type == "residential")
                    {
                        typology = 0;
                    }

                    GameObject bObj = new GameObject("Building_Procedural_" + bldg.id);
                    bObj.transform.parent = buildingsParent.transform;
                    bObj.isStatic = true;

                    // Apply distinct warning red material to documented source conflicts
                    Material chosenWallMat = isConflict ? warningRedMat : fallbackMats[bldgHash % fallbackMats.Length];

                    if (typology == 0)
                    {
                        float bldgHeight = Mathf.Clamp((sizeX + sizeZ) * 0.28f, 5.5f, 9.5f);
                        BuildTerracottaSlopingBuilding(bObj, bldg.shape, bldgHeight, minRoadEdgeDist, chosenWallMat, terracottaRoofMat, plinthMat);
                    }
                    else if (typology == 1)
                    {
                        float bldgHeight = Mathf.Clamp((sizeX + sizeZ) * 0.38f, 10.0f, 17.5f);
                        BuildStorefrontBuilding(bObj, bldg.shape, bldgHeight, centroid, chosenWallMat, storefrontMat, concreteCopingMat);
                    }
                    else
                    {
                        float bldgHeight = Mathf.Clamp((sizeX + sizeZ) * 0.44f, 14.0f, 25.0f);
                        BuildMultiStoryBuilding(bObj, bldg.shape, bldgHeight, centroid, chosenWallMat, waterTankMat, concreteCopingMat);
                    }

                    // Compound wall: only generate if building is clear of roads (>= 4.5m) and not a conflict
                    if (!isConflict && minRoadEdgeDist >= 4.5f)
                    {
                        BuildCompoundWall(bObj, bldg.shape, compoundWallMat);
                    }

                    // Visual Debugging: highlight conflicting road region in contrasting cyan
                    if (isConflict)
                    {
                        GameObject debugBadge = GameObject.CreatePrimitive(PrimitiveType.Cube);
                        debugBadge.name = "SourceConflictBadge_" + bldg.id;
                        debugBadge.transform.parent = bObj.transform;
                        debugBadge.transform.localPosition = new Vector3(centroid.x, 18.0f, centroid.y);
                        debugBadge.transform.localScale = new Vector3(3.0f, 1.0f, 3.0f);
                        Destroy(debugBadge.GetComponent<Collider>());
                        debugBadge.GetComponent<Renderer>().sharedMaterial = cyanHighlightMat;
                    }

                    fallbackPlacedCount++;
                }
            }

            Debug.Log($"RoadVisualizer: Placed {modelPlacedCount} frontage-aligned 3D models and {fallbackPlacedCount} procedural buildings ({conflictCount} documented source conflicts flagged).");
        }

        // Render Parks and Urban Green Spaces
        GameObject parksParent = GameObject.Find("Environment/Parks");
        if (parksParent == null) parksParent = new GameObject("SUMO_Parks");
        ClearChildren(parksParent);
        if (networkData.parks != null)
        {
            Material parkGrassMat = new Material(litShader);
            Color grassCol = new Color(0.20f, 0.44f, 0.18f, 1.0f);
            parkGrassMat.color = grassCol;
            if (parkGrassMat.HasProperty("_BaseColor")) parkGrassMat.SetColor("_BaseColor", grassCol);
            if (parkGrassMat.HasProperty("_Smoothness")) parkGrassMat.SetFloat("_Smoothness", 0.05f);

            foreach (var park in networkData.parks)
            {
                if (park.shape == null || park.shape.Length < 3) continue;
                GameObject pObj = new GameObject("Park_" + park.id);
                pObj.transform.parent = parksParent.transform;
                pObj.isStatic = true;
                MeshFilter pmf = pObj.AddComponent<MeshFilter>();
                MeshRenderer pmr = pObj.AddComponent<MeshRenderer>();
                pmr.sharedMaterial = parkGrassMat;
                pmf.mesh = GenerateJunctionMesh(park.shape);
            }
            Debug.Log($"RoadVisualizer: Placed {networkData.parks.Length} urban parks and green spaces.");
        }
        // Render Road Labels
        GameObject labelsParent = GameObject.Find("Environment/RoadLabels");
        if (labelsParent == null) labelsParent = new GameObject("SUMO_RoadLabels");
        ClearChildren(labelsParent);
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
        Vector3[] vertices = new Vector3[numPoints + 1];
        int[] triangles = new int[numPoints * 3];
        Vector2[] uvs = new Vector2[numPoints + 1];
        Vector3[] normals = new Vector3[numPoints + 1];
        
        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            vertices[i] = new Vector3(shape[i].x, 0.02f, shape[i].y);
            centroid += vertices[i];
            uvs[i] = new Vector2(shape[i].x / 4.0f, shape[i].y / 4.0f);
            normals[i] = Vector3.up;
        }
        centroid /= numPoints;
        vertices[numPoints] = centroid; // Center vertex
        uvs[numPoints] = new Vector2(centroid.x / 4.0f, centroid.z / 4.0f);
        normals[numPoints] = Vector3.up;

        // Calculate signed 2D area in XZ plane (SUMO X, Y) to determine winding
        float signedArea = 0f;
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            signedArea += (shape[i].x * shape[next].y - shape[next].x * shape[i].y);
        }
        
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            int tIdx = i * 3;
            
            // Check orientation of this specific triangle relative to centroid
            float uX = shape[next].x - centroid.x;
            float uZ = shape[next].y - centroid.z;
            float vX = shape[i].x - centroid.x;
            float vZ = shape[i].y - centroid.z;
            float crossY = uZ * vX - uX * vZ;

            // Single-sided upward winding facing +Y
            if (crossY >= 0f)
            {
                triangles[tIdx] = numPoints;
                triangles[tIdx + 1] = next;
                triangles[tIdx + 2] = i;
            }
            else
            {
                triangles[tIdx] = numPoints;
                triangles[tIdx + 1] = i;
                triangles[tIdx + 2] = next;
            }
        }
        
        Mesh mesh = new Mesh();
        mesh.vertices = vertices;
        mesh.triangles = triangles;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.RecalculateBounds();
        return mesh;
    }

    Mesh GenerateBuildingMesh(Point2D[] shape, float height)
    {
        int numPoints = shape.Length;
        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector2> uvs = new List<Vector2>();
        List<Vector3> normals = new List<Vector3>();

        // Calculate signed 2D area in XZ plane to determine boundary winding
        float signedArea = 0f;
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            signedArea += (shape[i].x * shape[next].y - shape[next].x * shape[i].y);
        }

        // Roof centroid
        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            centroid += new Vector3(shape[i].x, height, shape[i].y);
        }
        centroid /= numPoints;

        int roofStartIndex = verts.Count;
        verts.Add(centroid);
        uvs.Add(new Vector2(centroid.x / 4.0f, centroid.z / 4.0f));
        normals.Add(Vector3.up);
        
        for (int i = 0; i < numPoints; i++)
        {
            verts.Add(new Vector3(shape[i].x, height, shape[i].y));
            uvs.Add(new Vector2(shape[i].x / 4.0f, shape[i].y / 4.0f));
            normals.Add(Vector3.up);
        }

        // Roof Triangles (Single-sided facing +Y)
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            float uX = shape[next].x - centroid.x;
            float uZ = shape[next].y - centroid.z;
            float vX = shape[i].x - centroid.x;
            float vZ = shape[i].y - centroid.z;
            float crossY = uZ * vX - uX * vZ;

            if (crossY >= 0f)
            {
                tris.Add(roofStartIndex);
                tris.Add(roofStartIndex + 1 + next);
                tris.Add(roofStartIndex + 1 + i);
            }
            else
            {
                tris.Add(roofStartIndex);
                tris.Add(roofStartIndex + 1 + i);
                tris.Add(roofStartIndex + 1 + next);
            }
        }

        // Walls (Single-sided quads with outward-facing normals)
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            Vector3 bl = new Vector3(shape[i].x, 0, shape[i].y);
            Vector3 br = new Vector3(shape[next].x, 0, shape[next].y);
            Vector3 tl = new Vector3(shape[i].x, height, shape[i].y);
            Vector3 tr = new Vector3(shape[next].x, height, shape[next].y);

            Vector3 wallDir = (br - bl).normalized;
            Vector3 outNormal = (signedArea >= 0f) ? Vector3.Cross(Vector3.up, wallDir).normalized : -Vector3.Cross(Vector3.up, wallDir).normalized;

            int wStart = verts.Count;
            verts.Add(bl);
            verts.Add(br);
            verts.Add(tl);
            verts.Add(tr);

            normals.Add(outNormal);
            normals.Add(outNormal);
            normals.Add(outNormal);
            normals.Add(outNormal);

            float wallDist = Vector3.Distance(bl, br);
            uvs.Add(new Vector2(0f, 0f));
            uvs.Add(new Vector2(wallDist / 4f, 0f));
            uvs.Add(new Vector2(0f, height / 4f));
            uvs.Add(new Vector2(wallDist / 4f, height / 4f));

            if (signedArea >= 0f)
            {
                tris.Add(wStart);
                tris.Add(wStart + 2);
                tris.Add(wStart + 1);

                tris.Add(wStart + 1);
                tris.Add(wStart + 2);
                tris.Add(wStart + 3);
            }
            else
            {
                tris.Add(wStart);
                tris.Add(wStart + 1);
                tris.Add(wStart + 2);

                tris.Add(wStart + 1);
                tris.Add(wStart + 3);
                tris.Add(wStart + 2);
            }
        }

        Mesh mesh = new Mesh();
        mesh.vertices = verts.ToArray();
        mesh.triangles = tris.ToArray();
        mesh.uv = uvs.ToArray();
        mesh.normals = normals.ToArray();
        mesh.RecalculateBounds();
        return mesh;
    }

    Mesh GenerateLaneMesh(Point2D[] shape, float width)
    {
        int numPoints = shape.Length;
        Vector3[] vertices = new Vector3[numPoints * 2];
        int[] triangles = new int[(numPoints - 1) * 6];
        Vector2[] uvs = new Vector2[numPoints * 2];
        Vector3[] normals = new Vector3[numPoints * 2];

        float halfWidth = width / 2f;

        // Convert SUMO points to Unity points, elevated slightly to Y=0.02m to avoid ground Z-fighting
        Vector3[] pathPoints = new Vector3[numPoints];
        for (int i = 0; i < numPoints; i++)
        {
            pathPoints[i] = new Vector3(shape[i].x, 0.02f, shape[i].y);
        }

        float accumulatedDist = 0f;
        for (int i = 0; i < numPoints; i++)
        {
            if (i > 0) accumulatedDist += Vector3.Distance(pathPoints[i], pathPoints[i - 1]);

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

            // All road surface normals point directly upward (+Y)
            normals[i * 2] = Vector3.up;
            normals[i * 2 + 1] = Vector3.up;

            // Distance-based UV mapping: tiles asphalt texture every 4 meters
            float v = accumulatedDist / 4.0f;
            uvs[i * 2] = new Vector2(0f, v);
            uvs[i * 2 + 1] = new Vector2(1f, v);
        }

        for (int i = 0; i < numPoints - 1; i++)
        {
            int vIndex = i * 2;
            int tIndex = i * 6;

            // Single-sided upward quad (Clockwise looking down from +Y)
            triangles[tIndex] = vIndex;
            triangles[tIndex + 1] = vIndex + 2;
            triangles[tIndex + 2] = vIndex + 1;

            triangles[tIndex + 3] = vIndex + 1;
            triangles[tIndex + 4] = vIndex + 2;
            triangles[tIndex + 5] = vIndex + 3;
        }

        Mesh mesh = new Mesh();
        mesh.vertices = vertices;
        mesh.triangles = triangles;
        mesh.uv = uvs;
        mesh.normals = normals;
        mesh.RecalculateBounds();

        return mesh;
    }

    Vector3 SamplePointAlongShape3D(Point2D[] shape, float targetDist, out Vector3 forwardDir)
    {
        float accum = 0f;
        for (int i = 0; i < shape.Length - 1; i++)
        {
            Vector3 p1 = new Vector3(shape[i].x, 0.02f, shape[i].y);
            Vector3 p2 = new Vector3(shape[i + 1].x, 0.02f, shape[i + 1].y);
            float d = Vector3.Distance(p1, p2);

            if (accum + d >= targetDist)
            {
                float t = (d > 0.0001f) ? (targetDist - accum) / d : 0f;
                forwardDir = (p2 - p1).normalized;
                return Vector3.Lerp(p1, p2, t);
            }
            accum += d;
        }

        int last = shape.Length - 1;
        Vector3 lastP = new Vector3(shape[last].x, 0.02f, shape[last].y);
        Vector3 prevP = new Vector3(shape[last - 1].x, 0.02f, shape[last - 1].y);
        forwardDir = (lastP - prevP).normalized;
        return lastP;
    }

    Mesh GenerateSidewalkMesh(Point2D[] shape, float roadWidth, float sidewalkWidth, float curbHeight)
    {
        int numPoints = shape.Length;
        if (numPoints < 2) return null;

        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector2> uvs = new List<Vector2>();
        List<Vector3> normals = new List<Vector3>();

        float halfRoadWidth = roadWidth * 0.5f;
        float accumulatedDist = 0f;

        Vector3[] centerPts = new Vector3[numPoints];
        Vector3[] leftDirs = new Vector3[numPoints];

        for (int i = 0; i < numPoints; i++)
        {
            centerPts[i] = new Vector3(shape[i].x, 0.02f, shape[i].y);
        }

        for (int i = 0; i < numPoints; i++)
        {
            Vector3 fwd;
            if (i < numPoints - 1)
                fwd = (centerPts[i + 1] - centerPts[i]).normalized;
            else
                fwd = (centerPts[i] - centerPts[i - 1]).normalized;

            Vector3 right = Vector3.Cross(Vector3.up, fwd).normalized;
            leftDirs[i] = -right; // Left in left-hand drive
        }

        for (int i = 0; i < numPoints - 1; i++)
        {
            float segLen = Vector3.Distance(centerPts[i], centerPts[i + 1]);
            float v0 = accumulatedDist / 2.0f;
            float v1 = (accumulatedDist + segLen) / 2.0f;
            accumulatedDist += segLen;

            // Point A (i)
            Vector3 roadEdgeA = centerPts[i] + leftDirs[i] * halfRoadWidth;
            Vector3 curbTopA = roadEdgeA + Vector3.up * curbHeight;
            Vector3 walkOuterA = curbTopA + leftDirs[i] * sidewalkWidth;
            Vector3 groundDropA = walkOuterA - Vector3.up * (curbHeight + 0.07f);

            // Point B (i+1)
            Vector3 roadEdgeB = centerPts[i + 1] + leftDirs[i + 1] * halfRoadWidth;
            Vector3 curbTopB = roadEdgeB + Vector3.up * curbHeight;
            Vector3 walkOuterB = curbTopB + leftDirs[i + 1] * sidewalkWidth;
            Vector3 groundDropB = walkOuterB - Vector3.up * (curbHeight + 0.07f);

            // 1. Curb Face (vertical, facing road: -leftDirs)
            int cIdx = verts.Count;
            verts.Add(roadEdgeA);
            verts.Add(curbTopA);
            verts.Add(curbTopB);
            verts.Add(roadEdgeB);

            Vector3 curbNormal = -leftDirs[i];
            normals.Add(curbNormal);
            normals.Add(curbNormal);
            normals.Add(curbNormal);
            normals.Add(curbNormal);

            uvs.Add(new Vector2(0f, v0));
            uvs.Add(new Vector2(1f, v0));
            uvs.Add(new Vector2(1f, v1));
            uvs.Add(new Vector2(0f, v1));

            tris.Add(cIdx); tris.Add(cIdx + 1); tris.Add(cIdx + 2);
            tris.Add(cIdx); tris.Add(cIdx + 2); tris.Add(cIdx + 3);

            // 2. Sidewalk Walking Surface (horizontal, facing UP)
            int wIdx = verts.Count;
            verts.Add(curbTopA);
            verts.Add(walkOuterA);
            verts.Add(walkOuterB);
            verts.Add(curbTopB);

            normals.Add(Vector3.up);
            normals.Add(Vector3.up);
            normals.Add(Vector3.up);
            normals.Add(Vector3.up);

            uvs.Add(new Vector2(0f, v0));
            uvs.Add(new Vector2(1f, v0));
            uvs.Add(new Vector2(1f, v1));
            uvs.Add(new Vector2(0f, v1));

            tris.Add(wIdx); tris.Add(wIdx + 1); tris.Add(wIdx + 2);
            tris.Add(wIdx); tris.Add(wIdx + 2); tris.Add(wIdx + 3);

            // 3. Outer Ground Drop (vertical, facing outward: leftDirs)
            int dIdx = verts.Count;
            verts.Add(walkOuterA);
            verts.Add(groundDropA);
            verts.Add(groundDropB);
            verts.Add(walkOuterB);

            Vector3 dropNormal = leftDirs[i];
            normals.Add(dropNormal);
            normals.Add(dropNormal);
            normals.Add(dropNormal);
            normals.Add(dropNormal);

            uvs.Add(new Vector2(0f, v0));
            uvs.Add(new Vector2(1f, v0));
            uvs.Add(new Vector2(1f, v1));
            uvs.Add(new Vector2(0f, v1));

            tris.Add(dIdx); tris.Add(dIdx + 1); tris.Add(dIdx + 2);
            tris.Add(dIdx); tris.Add(dIdx + 2); tris.Add(dIdx + 3);
        }

        Mesh m = new Mesh();
        m.name = "SidewalkMesh";
        m.vertices = verts.ToArray();
        m.triangles = tris.ToArray();
        m.uv = uvs.ToArray();
        m.normals = normals.ToArray();
        m.RecalculateBounds();
        return m;
    }

    void CreateStreetlight(Transform parent, Vector3 basePos, Vector3 faceRoadDir, Material poleMat, Material lumMat)
    {
        GameObject lightObj = new GameObject("Streetlight");
        lightObj.transform.parent = parent;
        lightObj.transform.localPosition = basePos;
        lightObj.transform.localRotation = Quaternion.LookRotation(faceRoadDir, Vector3.up);
        lightObj.isStatic = true;

        GameObject pole = GameObject.CreatePrimitive(PrimitiveType.Cube);
        pole.name = "Pole";
        pole.transform.parent = lightObj.transform;
        pole.transform.localPosition = new Vector3(0f, 3.25f, 0f);
        pole.transform.localRotation = Quaternion.identity;
        pole.transform.localScale = new Vector3(0.12f, 6.5f, 0.12f);
        Destroy(pole.GetComponent<Collider>());
        pole.GetComponent<Renderer>().sharedMaterial = poleMat;

        GameObject arm = GameObject.CreatePrimitive(PrimitiveType.Cube);
        arm.name = "Arm";
        arm.transform.parent = lightObj.transform;
        arm.transform.localPosition = new Vector3(0f, 6.35f, 0.75f);
        arm.transform.localRotation = Quaternion.identity;
        arm.transform.localScale = new Vector3(0.10f, 0.10f, 1.5f);
        Destroy(arm.GetComponent<Collider>());
        arm.GetComponent<Renderer>().sharedMaterial = poleMat;

        GameObject lum = GameObject.CreatePrimitive(PrimitiveType.Cube);
        lum.name = "Luminaire";
        lum.transform.parent = lightObj.transform;
        lum.transform.localPosition = new Vector3(0f, 6.30f, 1.45f);
        lum.transform.localRotation = Quaternion.identity;
        lum.transform.localScale = new Vector3(0.35f, 0.14f, 0.24f);
        Destroy(lum.GetComponent<Collider>());
        lum.GetComponent<Renderer>().sharedMaterial = lumMat;
    }

    void BuildTerracottaSlopingBuilding(GameObject root, Point2D[] shape, float height, float roadDist, Material wallMat, Material roofMat, Material plinthMat)
    {
        // 1. Foundation Plinth (0m to 0.65m)
        GameObject plinthObj = new GameObject("Plinth");
        plinthObj.transform.parent = root.transform;
        MeshFilter pmf = plinthObj.AddComponent<MeshFilter>();
        MeshRenderer pmr = plinthObj.AddComponent<MeshRenderer>();
        pmr.sharedMaterial = plinthMat;
        pmf.mesh = GenerateExtrudedWallMesh(shape, 0f, 0.65f);

        // 2. Main Wall Body (0.65m to height)
        GameObject wallObj = new GameObject("Walls");
        wallObj.transform.parent = root.transform;
        MeshFilter wmf = wallObj.AddComponent<MeshFilter>();
        MeshRenderer wmr = wallObj.AddComponent<MeshRenderer>();
        wmr.sharedMaterial = wallMat;
        wmf.mesh = GenerateExtrudedWallMesh(shape, 0.65f, height);

        // 3. Mangaluru Pitched/Hipped Terracotta Roof
        float overhang = (roadDist >= 3.2f) ? 0.32f : 0f;
        GameObject roofObj = new GameObject("TerracottaRoof");
        roofObj.transform.parent = root.transform;
        MeshFilter rmf = roofObj.AddComponent<MeshFilter>();
        MeshRenderer rmr = roofObj.AddComponent<MeshRenderer>();
        rmr.sharedMaterial = roofMat;
        rmf.mesh = GenerateTerracottaRoofMesh(shape, height, 2.6f, overhang);
    }

    void BuildStorefrontBuilding(GameObject root, Point2D[] shape, float height, Vector2 centroid, Material wallMat, Material storeMat, Material copingMat)
    {
        // 1. Ground Floor Commercial Storefront (0m to 3.5m)
        GameObject storeObj = new GameObject("StorefrontGround");
        storeObj.transform.parent = root.transform;
        MeshFilter smf = storeObj.AddComponent<MeshFilter>();
        MeshRenderer smr = storeObj.AddComponent<MeshRenderer>();
        smr.sharedMaterial = storeMat;
        smf.mesh = GenerateExtrudedWallMesh(shape, 0f, 3.5f);

        // 2. Upper Commercial Floors (3.5m to height)
        GameObject upperObj = new GameObject("UpperFloors");
        upperObj.transform.parent = root.transform;
        MeshFilter umf = upperObj.AddComponent<MeshFilter>();
        MeshRenderer umr = upperObj.AddComponent<MeshRenderer>();
        umr.sharedMaterial = wallMat;
        umf.mesh = GenerateExtrudedWallMesh(shape, 3.5f, height);

        // 3. Flat Roof Slab
        GameObject roofObj = new GameObject("FlatRoof");
        roofObj.transform.parent = root.transform;
        MeshFilter rmf = roofObj.AddComponent<MeshFilter>();
        MeshRenderer rmr = roofObj.AddComponent<MeshRenderer>();
        rmr.sharedMaterial = copingMat;
        rmf.mesh = GenerateFlatRoofMesh(shape, height);

        // 4. Perimeter Parapet Wall (height to height + 0.85m)
        GameObject parapetObj = new GameObject("Parapet");
        parapetObj.transform.parent = root.transform;
        MeshFilter pmf = parapetObj.AddComponent<MeshFilter>();
        MeshRenderer pmr = parapetObj.AddComponent<MeshRenderer>();
        pmr.sharedMaterial = wallMat;
        pmf.mesh = GenerateExtrudedWallMesh(shape, height, height + 0.85f);

        // 5. Rooftop Lift Room / Stair Penthouse
        GameObject liftRoom = GameObject.CreatePrimitive(PrimitiveType.Cube);
        liftRoom.name = "StairPenthouse";
        liftRoom.transform.parent = root.transform;
        liftRoom.transform.localPosition = new Vector3(centroid.x, height + 1.3f, centroid.y);
        liftRoom.transform.localScale = new Vector3(3.8f, 2.6f, 3.8f);
        Destroy(liftRoom.GetComponent<Collider>());
        liftRoom.GetComponent<Renderer>().sharedMaterial = wallMat;
    }

    void BuildMultiStoryBuilding(GameObject root, Point2D[] shape, float height, Vector2 centroid, Material wallMat, Material tankMat, Material copingMat)
    {
        // 1. Multi-Story Wall Body
        GameObject wallObj = new GameObject("Walls");
        wallObj.transform.parent = root.transform;
        MeshFilter wmf = wallObj.AddComponent<MeshFilter>();
        MeshRenderer wmr = wallObj.AddComponent<MeshRenderer>();
        wmr.sharedMaterial = wallMat;
        wmf.mesh = GenerateExtrudedWallMesh(shape, 0f, height);

        // 2. Flat Roof Slab
        GameObject roofObj = new GameObject("FlatRoof");
        roofObj.transform.parent = root.transform;
        MeshFilter rmf = roofObj.AddComponent<MeshFilter>();
        MeshRenderer rmr = roofObj.AddComponent<MeshRenderer>();
        rmr.sharedMaterial = copingMat;
        rmf.mesh = GenerateFlatRoofMesh(shape, height);

        // 3. Perimeter Parapet Wall
        GameObject parapetObj = new GameObject("Parapet");
        parapetObj.transform.parent = root.transform;
        MeshFilter pmf = parapetObj.AddComponent<MeshFilter>();
        MeshRenderer pmr = parapetObj.AddComponent<MeshRenderer>();
        pmr.sharedMaterial = wallMat;
        pmf.mesh = GenerateExtrudedWallMesh(shape, height, height + 0.80f);

        // 4. Overhead Water Storage Tanks (Twin Cylinders)
        for (int t = -1; t <= 1; t += 2)
        {
            GameObject tank = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            tank.name = "WaterTank_" + (t > 0 ? "1" : "2");
            tank.transform.parent = root.transform;
            tank.transform.localPosition = new Vector3(centroid.x + t * 1.5f, height + 0.95f, centroid.y);
            tank.transform.localScale = new Vector3(1.3f, 0.90f, 1.3f);
            Destroy(tank.GetComponent<Collider>());
            tank.GetComponent<Renderer>().sharedMaterial = tankMat;
        }
    }

    void BuildCompoundWall(GameObject root, Point2D[] shape, Material wallMat)
    {
        int numPoints = shape.Length;
        if (numPoints < 3) return;

        int longestIdx = 0;
        float maxLen = 0f;
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            float d = Vector2.Distance(new Vector2(shape[i].x, shape[i].y), new Vector2(shape[next].x, shape[next].y));
            if (d > maxLen)
            {
                maxLen = d;
                longestIdx = i;
            }
        }

        GameObject wallObj = new GameObject("CompoundWall");
        wallObj.transform.parent = root.transform;
        MeshFilter wmf = wallObj.AddComponent<MeshFilter>();
        MeshRenderer wmr = wallObj.AddComponent<MeshRenderer>();
        wmr.sharedMaterial = wallMat;

        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector3> normals = new List<Vector3>();
        List<Vector2> uvs = new List<Vector2>();

        float wallHeight = 1.2f;

        for (int i = 0; i < numPoints; i++)
        {
            if (i == longestIdx && maxLen > 5.0f) continue;

            int next = (i + 1) % numPoints;
            Vector3 bl = new Vector3(shape[i].x, 0f, shape[i].y);
            Vector3 br = new Vector3(shape[next].x, 0f, shape[next].y);
            Vector3 tl = new Vector3(shape[i].x, wallHeight, shape[i].y);
            Vector3 tr = new Vector3(shape[next].x, wallHeight, shape[next].y);

            Vector3 dir = (br - bl).normalized;
            Vector3 n = Vector3.Cross(Vector3.up, dir).normalized;

            int vStart = verts.Count;
            verts.Add(bl); verts.Add(br); verts.Add(tl); verts.Add(tr);
            normals.Add(n); normals.Add(n); normals.Add(n); normals.Add(n);
            uvs.Add(new Vector2(0f, 0f)); uvs.Add(new Vector2(1f, 0f));
            uvs.Add(new Vector2(0f, 1f)); uvs.Add(new Vector2(1f, 1f));

            tris.Add(vStart); tris.Add(vStart + 2); tris.Add(vStart + 1);
            tris.Add(vStart + 1); tris.Add(vStart + 2); tris.Add(vStart + 3);
        }

        Mesh m = new Mesh();
        m.name = "CompoundWallMesh";
        m.vertices = verts.ToArray();
        m.triangles = tris.ToArray();
        m.normals = normals.ToArray();
        m.uv = uvs.ToArray();
        m.RecalculateBounds();
        wmf.mesh = m;
    }

    Mesh GenerateExtrudedWallMesh(Point2D[] shape, float baseHeight, float topHeight)
    {
        int numPoints = shape.Length;
        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector2> uvs = new List<Vector2>();
        List<Vector3> normals = new List<Vector3>();

        float signedArea = 0f;
        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            signedArea += (shape[i].x * shape[next].y - shape[next].x * shape[i].y);
        }

        float wallHeight = topHeight - baseHeight;

        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            Vector3 bl = new Vector3(shape[i].x, baseHeight, shape[i].y);
            Vector3 br = new Vector3(shape[next].x, baseHeight, shape[next].y);
            Vector3 tl = new Vector3(shape[i].x, topHeight, shape[i].y);
            Vector3 tr = new Vector3(shape[next].x, topHeight, shape[next].y);

            Vector3 wallDir = (br - bl).normalized;
            Vector3 outNormal = (signedArea >= 0f) ? Vector3.Cross(Vector3.up, wallDir).normalized : -Vector3.Cross(Vector3.up, wallDir).normalized;

            int wStart = verts.Count;
            verts.Add(bl);
            verts.Add(br);
            verts.Add(tl);
            verts.Add(tr);

            normals.Add(outNormal);
            normals.Add(outNormal);
            normals.Add(outNormal);
            normals.Add(outNormal);

            float wallDist = Vector3.Distance(bl, br);
            uvs.Add(new Vector2(0f, 0f));
            uvs.Add(new Vector2(wallDist / 4f, 0f));
            uvs.Add(new Vector2(0f, wallHeight / 4f));
            uvs.Add(new Vector2(wallDist / 4f, wallHeight / 4f));

            if (signedArea >= 0f)
            {
                tris.Add(wStart);
                tris.Add(wStart + 2);
                tris.Add(wStart + 1);

                tris.Add(wStart + 1);
                tris.Add(wStart + 2);
                tris.Add(wStart + 3);
            }
            else
            {
                tris.Add(wStart);
                tris.Add(wStart + 1);
                tris.Add(wStart + 2);

                tris.Add(wStart + 1);
                tris.Add(wStart + 3);
                tris.Add(wStart + 2);
            }
        }

        Mesh mesh = new Mesh();
        mesh.vertices = verts.ToArray();
        mesh.triangles = tris.ToArray();
        mesh.uv = uvs.ToArray();
        mesh.normals = normals.ToArray();
        mesh.RecalculateBounds();
        return mesh;
    }

    Mesh GenerateFlatRoofMesh(Point2D[] shape, float height)
    {
        int numPoints = shape.Length;
        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector2> uvs = new List<Vector2>();
        List<Vector3> normals = new List<Vector3>();

        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            centroid += new Vector3(shape[i].x, height, shape[i].y);
        }
        centroid /= numPoints;

        int roofStartIndex = verts.Count;
        verts.Add(centroid);
        uvs.Add(new Vector2(centroid.x / 4.0f, centroid.z / 4.0f));
        normals.Add(Vector3.up);

        for (int i = 0; i < numPoints; i++)
        {
            verts.Add(new Vector3(shape[i].x, height, shape[i].y));
            uvs.Add(new Vector2(shape[i].x / 4.0f, shape[i].y / 4.0f));
            normals.Add(Vector3.up);
        }

        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            float uX = shape[next].x - centroid.x;
            float uZ = shape[next].y - centroid.z;
            float vX = shape[i].x - centroid.x;
            float vZ = shape[i].y - centroid.z;
            float crossY = uZ * vX - uX * vZ;

            if (crossY >= 0f)
            {
                tris.Add(roofStartIndex);
                tris.Add(roofStartIndex + 1 + next);
                tris.Add(roofStartIndex + 1 + i);
            }
            else
            {
                tris.Add(roofStartIndex);
                tris.Add(roofStartIndex + 1 + i);
                tris.Add(roofStartIndex + 1 + next);
            }
        }

        Mesh mesh = new Mesh();
        mesh.vertices = verts.ToArray();
        mesh.triangles = tris.ToArray();
        mesh.uv = uvs.ToArray();
        mesh.normals = normals.ToArray();
        mesh.RecalculateBounds();
        return mesh;
    }

    Mesh GenerateTerracottaRoofMesh(Point2D[] shape, float wallHeight, float apexHeight, float overhang)
    {
        int numPoints = shape.Length;
        List<Vector3> verts = new List<Vector3>();
        List<int> tris = new List<int>();
        List<Vector2> uvs = new List<Vector2>();
        List<Vector3> normals = new List<Vector3>();

        Vector3 centroid = Vector3.zero;
        for (int i = 0; i < numPoints; i++)
        {
            centroid += new Vector3(shape[i].x, wallHeight, shape[i].y);
        }
        centroid /= numPoints;

        Vector3 apex = centroid + Vector3.up * apexHeight;
        int apexIndex = verts.Count;
        verts.Add(apex);
        uvs.Add(new Vector2(centroid.x / 3.0f, centroid.z / 3.0f));
        normals.Add(Vector3.up);

        Vector3[] eaves = new Vector3[numPoints];
        for (int i = 0; i < numPoints; i++)
        {
            Vector2 toPt = new Vector2(shape[i].x - centroid.x, shape[i].y - centroid.z);
            Vector2 offset = (toPt.sqrMagnitude > 0.001f) ? toPt.normalized * overhang : Vector2.zero;
            eaves[i] = new Vector3(shape[i].x + offset.x, wallHeight, shape[i].y + offset.y);

            verts.Add(eaves[i]);
            uvs.Add(new Vector2(eaves[i].x / 3.0f, eaves[i].z / 3.0f));
            normals.Add(Vector3.up);
        }

        for (int i = 0; i < numPoints; i++)
        {
            int next = (i + 1) % numPoints;
            float uX = eaves[next].x - centroid.x;
            float uZ = eaves[next].z - centroid.z;
            float vX = eaves[i].x - centroid.x;
            float vZ = eaves[i].z - centroid.z;
            float crossY = uZ * vX - uX * vZ;

            if (crossY >= 0f)
            {
                tris.Add(apexIndex);
                tris.Add(apexIndex + 1 + next);
                tris.Add(apexIndex + 1 + i);
            }
            else
            {
                tris.Add(apexIndex);
                tris.Add(apexIndex + 1 + i);
                tris.Add(apexIndex + 1 + next);
            }
        }

        if (overhang > 0.01f)
        {
            for (int i = 0; i < numPoints; i++)
            {
                int next = (i + 1) % numPoints;
                Vector3 wallA = new Vector3(shape[i].x, wallHeight, shape[i].y);
                Vector3 wallB = new Vector3(shape[next].x, wallHeight, shape[next].y);
                Vector3 eA = eaves[i];
                Vector3 eB = eaves[next];

                int sStart = verts.Count;
                verts.Add(wallA); verts.Add(wallB); verts.Add(eA); verts.Add(eB);
                normals.Add(-Vector3.up); normals.Add(-Vector3.up); normals.Add(-Vector3.up); normals.Add(-Vector3.up);
                uvs.Add(new Vector2(0f, 0f)); uvs.Add(new Vector2(1f, 0f));
                uvs.Add(new Vector2(0f, 1f)); uvs.Add(new Vector2(1f, 1f));

                tris.Add(sStart); tris.Add(sStart + 1); tris.Add(sStart + 2);
                tris.Add(sStart + 1); tris.Add(sStart + 3); tris.Add(sStart + 2);
            }
        }

        Mesh mesh = new Mesh();
        mesh.vertices = verts.ToArray();
        mesh.triangles = tris.ToArray();
        mesh.uv = uvs.ToArray();
        mesh.normals = normals.ToArray();
        mesh.RecalculateNormals();
        mesh.RecalculateBounds();
        return mesh;
    }

    private static bool PointInPolygon(Vector2 pt, Vector2[] poly)
    {
        if (poly == null || poly.Length < 3) return false;
        bool inside = false;
        for (int i = 0, j = poly.Length - 1; i < poly.Length; j = i++)
        {
            if (((poly[i].y > pt.y) != (poly[j].y > pt.y)) &&
                (pt.x < (poly[j].x - poly[i].x) * (pt.y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x))
            {
                inside = !inside;
            }
        }
        return inside;
    }
}
