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
    public bool is_tls;
    public float x;
    public float y;
    public Point2D[] shape;
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
}

public class RoadVisualizer : MonoBehaviour
{
    public string jsonFileName = "RoadNetwork.json";
    public Material roadMaterial;
    public float defaultLineWidth = 3.2f; // Standard lane width

    void Start()
    {
        // Bootstrap essential receivers if they are missing from the scene
        if (gameObject.GetComponent<HospitalVisualizer>() == null)
        {
            gameObject.AddComponent<HospitalVisualizer>();
            Debug.Log("RoadVisualizer: Bootstrapped missing HospitalVisualizer.");
        }

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
        
        GameObject tlsParent = GameObject.Find("Traffic/TrafficSignals");
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

                if (junc.is_tls)
                {
                    GameObject tlsRoot = new GameObject("TLS_" + junc.id);
                    tlsRoot.transform.parent = tlsParent.transform;
                    
                    Vector3 signalPos = new Vector3(junc.x, 0f, junc.y);
                    if (junc.shape != null && junc.shape.Length > 0)
                    {
                        signalPos = new Vector3(junc.shape[0].x, 0f, junc.shape[0].y);
                    }
                    tlsRoot.transform.localPosition = signalPos;
                    if (Vector3.Distance(signalPos, new Vector3(junc.x, 0f, junc.y)) > 0.1f)
                    {
                        tlsRoot.transform.LookAt(new Vector3(junc.x, 0f, junc.y));
                    }

                    // Pole
                    GameObject pole = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                    pole.name = "Pole";
                    pole.transform.parent = tlsRoot.transform;
                    pole.transform.localPosition = new Vector3(0, 3f, 0); // 6m tall
                    pole.transform.localScale = new Vector3(0.2f, 3f, 0.2f);
                    Destroy(pole.GetComponent<Collider>());
                    Material poleMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                    poleMat.color = new Color(0.2f, 0.2f, 0.2f);
                    pole.GetComponent<Renderer>().material = poleMat;

                    // Signal Head
                    GameObject head = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    head.name = "Head";
                    head.transform.parent = tlsRoot.transform;
                    head.transform.localPosition = new Vector3(0, 5.5f, 0);
                    head.transform.localScale = new Vector3(0.5f, 1.5f, 0.5f);
                    Destroy(head.GetComponent<Collider>());
                    
                    Material headMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                    headMat.color = Color.black;
                    head.GetComponent<Renderer>().material = headMat;
                    
                    // Lights (R, Y, G)
                    // Placed at Z = -0.27f to protrude cleanly out of the 0.5 scale head (0.25 radius)
                    CreateSignalLight(head.transform, "Light_R", new Vector3(0, 0.5f, -0.27f), Color.red);
                    CreateSignalLight(head.transform, "Light_Y", new Vector3(0, 0f, -0.27f), Color.yellow);
                    CreateSignalLight(head.transform, "Light_G", new Vector3(0, -0.5f, -0.27f), Color.green);
                }
            }
        }
        
        // Render Buildings
        GameObject buildingsParent = GameObject.Find("Environment/Buildings");
        if (buildingsParent == null) buildingsParent = new GameObject("SUMO_Buildings");
        if (networkData.buildings != null)
        {
            Material[] bldgMats = new Material[4];
            Color[] colors = { 
                new Color(0.7f, 0.7f, 0.7f),   // Light gray
                new Color(0.75f, 0.72f, 0.65f), // Beige
                new Color(0.65f, 0.7f, 0.75f), // Pale blue-gray
                new Color(0.6f, 0.6f, 0.6f)    // Medium gray
            };
            for(int i=0; i<4; i++) {
                bldgMats[i] = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                bldgMats[i].color = colors[i];
            }
            
            // Setup simple random determinism so buildings don't flicker on reload
            Random.InitState(42);
            
            foreach (BuildingData bldg in networkData.buildings)
            {
                if (bldg.shape == null || bldg.shape.Length < 3) continue;
                
                // Calculate bounding box
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
                
                // Random height based on footprint size to look somewhat realistic
                float height = Mathf.Clamp((sizeX + sizeZ) * 0.5f, 5f, 40f);
                
                GameObject bObj = new GameObject("Building_" + bldg.id);
                bObj.transform.parent = buildingsParent.transform;
                bObj.isStatic = true;
                
                MeshFilter mf = bObj.AddComponent<MeshFilter>();
                MeshRenderer mr = bObj.AddComponent<MeshRenderer>();
                mr.material = bldgMats[Random.Range(0, 4)];
                
                mf.mesh = GenerateBuildingMesh(bldg.shape, height);
            }
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

    void CreateSignalLight(Transform parent, string name, Vector3 localPos, Color defaultColor)
    {
        GameObject light = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        light.name = name;
        light.transform.parent = parent;
        light.transform.localPosition = localPos;
        // Squashed sphere to look like a light bulb lens
        light.transform.localScale = new Vector3(0.4f, 0.4f, 0.1f);
        Destroy(light.GetComponent<Collider>());
        
        Material mat = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
        mat.color = new Color(defaultColor.r * 0.15f, defaultColor.g * 0.15f, defaultColor.b * 0.15f); // dim
        light.GetComponent<Renderer>().material = mat;
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
