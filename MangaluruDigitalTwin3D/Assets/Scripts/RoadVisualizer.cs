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
public class RoadNetworkData {
    public EdgeData[] edges;
    public JunctionData[] junctions;
    public BuildingData[] buildings;
}

public class RoadVisualizer : MonoBehaviour
{
    public string jsonFileName = "RoadNetwork.json";
    public Material roadMaterial;
    public float defaultLineWidth = 3.2f; // Standard lane width

    void Start()
    {
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
        
        Material markingMat = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
        markingMat.color = Color.white;
        
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
                lr.useWorldSpace = true;
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
                    
                    MeshFilter mf = juncObj.AddComponent<MeshFilter>();
                    MeshRenderer mr = juncObj.AddComponent<MeshRenderer>();
                    mr.material = mat;
                    
                    mf.mesh = GenerateJunctionMesh(junc.shape);
                }

                if (junc.is_tls)
                {
                    GameObject tlsObj = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                    tlsObj.name = "TLS_" + junc.id;
                    tlsObj.transform.parent = tlsParent.transform;
                    tlsObj.transform.position = new Vector3(junc.x, 10f, junc.y); // Hovering high above junction
                    tlsObj.transform.localScale = new Vector3(5f, 5f, 5f);
                    
                    // Remove collider to save performance
                    Destroy(tlsObj.GetComponent<Collider>());
                    
                    Material tlsMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                    tlsMat.color = Color.black; // default off state
                    tlsObj.GetComponent<Renderer>().material = tlsMat;
                }
            }
        }
        
        // Render Buildings
        GameObject buildingsParent = GameObject.Find("Environment/Buildings");
        if (buildingsParent == null) buildingsParent = new GameObject("SUMO_Buildings");
        if (networkData.buildings != null)
        {
            Material bldgMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            bldgMat.color = new Color(0.7f, 0.7f, 0.7f); // Light gray buildings
            
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
                
                GameObject bObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
                bObj.name = "Building_" + bldg.id;
                bObj.transform.parent = buildingsParent.transform;
                bObj.transform.position = new Vector3(centerX, height / 2f, centerZ);
                bObj.transform.localScale = new Vector3(sizeX, height, sizeZ);
                
                bObj.GetComponent<Renderer>().material = bldgMat;
                Destroy(bObj.GetComponent<Collider>());
            }
        }
        
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
