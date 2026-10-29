using UnityEngine;
using System.IO;
using System.Collections.Generic;

public class EnvironmentDecorator : MonoBehaviour
{
    public int maxTrees = 65;
    public string jsonFileName = "RoadNetwork.json";

    private bool hasDecorated = false;

    // Materials
    private Material trunkMaterial;
    private Material canopyMaterialLush;
    private Material canopyMaterialGolden;

    void Start()
    {
        if (hasDecorated) return;
        hasDecorated = true;
        DecorateEnvironment();
    }

    public void ForceRegenerate()
    {
        hasDecorated = false;
        DecorateEnvironment();
    }

    private void EnsureMaterials()
    {
        Shader shader = Shader.Find("Universal Render Pipeline/Lit");
        if (shader == null) shader = Shader.Find("Standard");
        if (shader == null) shader = Shader.Find("Diffuse");

        if (trunkMaterial == null)
        {
            trunkMaterial = new Material(shader);
            trunkMaterial.name = "TreeTrunk_Mat";
            trunkMaterial.color = new Color(0.36f, 0.24f, 0.15f); // Rich dark bark
        }
        if (canopyMaterialLush == null)
        {
            canopyMaterialLush = new Material(shader);
            canopyMaterialLush.name = "Canopy_Lush_Mat";
            canopyMaterialLush.color = new Color(0.18f, 0.48f, 0.16f); // Tropical deep green
        }
        if (canopyMaterialGolden == null)
        {
            canopyMaterialGolden = new Material(shader);
            canopyMaterialGolden.name = "Canopy_Golden_Mat";
            canopyMaterialGolden.color = new Color(0.24f, 0.54f, 0.20f); // Vibrant light green
        }
    }

    public void DecorateEnvironment()
    {
        string filePath = Path.Combine(Application.dataPath, "Generated", jsonFileName);
        if (!File.Exists(filePath))
        {
            Debug.LogWarning("EnvironmentDecorator: RoadNetwork.json not found, skipping tree placement.");
            return;
        }

        string jsonContent = File.ReadAllText(filePath);
        RoadNetworkData networkData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);
        if (networkData == null || networkData.edges == null)
        {
            return;
        }

        EnsureMaterials();

        // Parent container
        GameObject treesParent = GameObject.Find("Environment/Trees");
        if (treesParent == null) treesParent = GameObject.Find("MangaluruDigitalTwin/Environment/Trees");
        if (treesParent == null) treesParent = GameObject.Find("Trees");
        if (treesParent == null)
        {
            treesParent = new GameObject("Trees");
            treesParent.transform.SetParent(transform, false);
        }

        // Clean out any existing children to avoid duplicates
        for (int i = treesParent.transform.childCount - 1; i >= 0; i--)
        {
            DestroyImmediate(treesParent.transform.GetChild(i).gameObject);
        }

        // Pre-build building bounding boxes to prevent tree-building clipping
        List<Bounds2D> bldgBounds = new List<Bounds2D>();
        if (networkData.buildings != null)
        {
            foreach (var b in networkData.buildings)
            {
                if (b.shape == null || b.shape.Length < 3) continue;
                float minX = float.MaxValue, minZ = float.MaxValue;
                float maxX = float.MinValue, maxZ = float.MinValue;
                foreach (var pt in b.shape)
                {
                    if (pt.x < minX) minX = pt.x;
                    if (pt.x > maxX) maxX = pt.x;
                    if (pt.y < minZ) minZ = pt.y;
                    if (pt.y > maxZ) maxZ = pt.y;
                }
                bldgBounds.Add(new Bounds2D(minX - 2.5f, minZ - 2.5f, maxX + 2.5f, maxZ + 2.5f));
            }
        }

        // Collect road lane segments to ensure clearance
        List<RoadSegmentSimple> roadSegments = new List<RoadSegmentSimple>();
        foreach (var edge in networkData.edges)
        {
            if (edge.lanes == null) continue;
            foreach (var lane in edge.lanes)
            {
                if (lane.shape == null || lane.shape.Length < 2) continue;
                float w = lane.width > 0 ? lane.width : 3.2f;
                for (int i = 0; i < lane.shape.Length - 1; i++)
                {
                    roadSegments.Add(new RoadSegmentSimple
                    {
                        p1 = new Vector2(lane.shape[i].x, lane.shape[i].y),
                        p2 = new Vector2(lane.shape[i+1].x, lane.shape[i+1].y),
                        halfWidth = w * 0.5f
                    });
                }
            }
        }

        // Hospital Exclusion Zones (>= 35m from any hospital emergency entrance)
        List<Vector2> hospitalExclusions = new List<Vector2>();
        if (networkData.hospitals != null)
        {
            foreach (var h in networkData.hospitals)
            {
                hospitalExclusions.Add(new Vector2(h.x, h.y));
            }
        }

        // Junction Exclusion Zones (>= 22m from intersections)
        List<Vector2> junctionExclusions = new List<Vector2>();
        if (networkData.junctions != null)
        {
            foreach (var j in networkData.junctions)
            {
                junctionExclusions.Add(new Vector2(j.x, j.y));
            }
        }

        // Deterministic random seed
        Random.InitState(101);

        int placedTrees = 0;

        // Roadside Verge Planting: sample along major corridors
        foreach (var edge in networkData.edges)
        {
            if (placedTrees >= maxTrees) break;
            if (edge.lanes == null || edge.lanes.Length == 0) continue;

            LaneData lane = edge.lanes[0];
            if (lane.shape == null || lane.shape.Length < 2) continue;

            float edgeLength = 0f;
            for (int i = 0; i < lane.shape.Length - 1; i++)
            {
                edgeLength += Vector2.Distance(new Vector2(lane.shape[i].x, lane.shape[i].y),
                                               new Vector2(lane.shape[i+1].x, lane.shape[i+1].y));
            }

            // Only plant along long road corridors (>= 45m)
            if (edgeLength < 45.0f) continue;

            // Sample points along edge at ~45m intervals
            int intervals = Mathf.FloorToInt(edgeLength / 45.0f);
            for (int k = 1; k <= intervals; k++)
            {
                if (placedTrees >= maxTrees) break;

                float targetDist = k * (edgeLength / (intervals + 1));
                Vector2 samplePos = SamplePointAlongShape(lane.shape, targetDist, out Vector2 forwardDir);

                // Offset to roadside verge
                Vector2 normal = new Vector2(-forwardDir.y, forwardDir.x).normalized;
                float roadsideOffset = (lane.width > 0 ? lane.width : 3.2f) * 0.5f + 3.2f; // ~4.8m from centerline

                // Alternate sides to prevent tunnel clustering
                int side = (k % 2 == 0) ? 1 : -1;
                Vector2 treePos = samplePos + normal * (roadsideOffset * side);

                // Urban bounds check
                if (treePos.x < 600f || treePos.x > 2600f || treePos.y < 900f || treePos.y > 2450f)
                    continue;

                // Hospital exclusion check
                bool nearHospital = false;
                foreach (var hPos in hospitalExclusions)
                {
                    if (Vector2.Distance(treePos, hPos) < 35.0f) { nearHospital = true; break; }
                }
                if (nearHospital) continue;

                // Junction exclusion check
                bool nearJunction = false;
                foreach (var jPos in junctionExclusions)
                {
                    if (Vector2.Distance(treePos, jPos) < 22.0f) { nearJunction = true; break; }
                }
                if (nearJunction) continue;

                // Clearance against road lanes (>= 2.2m from outer lane edge)
                bool roadClear = true;
                foreach (var seg in roadSegments)
                {
                    float d = DistancePointToSegment(treePos, seg.p1, seg.p2);
                    if (d < seg.halfWidth + 2.2f)
                    {
                        roadClear = false;
                        break;
                    }
                }
                if (!roadClear) continue;

                // Clearance against building bounding boxes
                bool bldgClear = true;
                foreach (var b in bldgBounds)
                {
                    if (b.Contains(treePos.x, treePos.y))
                    {
                        bldgClear = false;
                        break;
                    }
                }
                if (!bldgClear) continue;

                // Procedural Tree Generation: Realistic Indian Coastal Urban Typologies
                // 0 = Spreading Gulmohar / Rain Tree (Umbrella canopy, high clearance)
                // 1 = Coastal Royal Palm (Tall slender trunk, top frond crown)
                // 2 = Columnar Ashoka Tree (Sleek upright form)
                int treeTypology = placedTrees % 3;
                GameObject tree = CreateProceduralTree(placedTrees, treePos, treeTypology);
                tree.transform.SetParent(treesParent.transform, true);
                tree.isStatic = true;

                placedTrees++;
            }
        }

        Debug.Log($"EnvironmentDecorator: Successfully placed {placedTrees} roadside trees with verified road, junction, and hospital clearance.");
    }

    private GameObject CreateProceduralTree(int index, Vector2 pos, int typology)
    {
        GameObject tree = new GameObject($"RoadsideTree_{index}");
        tree.transform.position = new Vector3(pos.x, 0f, pos.y);

        if (typology == 0)
        {
            // Typology 0: Spreading Umbrella Tree (Rain Tree / Gulmohar)
            // Under-canopy clearance: 2.8m (ground level 100% visible)
            float trunkRadius = 0.22f;
            float trunkHeight = 2.8f;
            float canopyRadius = 2.6f;

            // Trunk
            GameObject trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.name = "Trunk";
            trunk.transform.parent = tree.transform;
            trunk.transform.localPosition = new Vector3(0f, trunkHeight * 0.5f, 0f);
            trunk.transform.localScale = new Vector3(trunkRadius * 2f, trunkHeight * 0.5f, trunkRadius * 2f);
            DestroyImmediate(trunk.GetComponent<Collider>());
            trunk.GetComponent<Renderer>().sharedMaterial = trunkMaterial;

            // Spreading Tiered Canopy
            GameObject canopy1 = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            canopy1.name = "Canopy_Base";
            canopy1.transform.parent = tree.transform;
            canopy1.transform.localPosition = new Vector3(0f, trunkHeight + 1.1f, 0f);
            canopy1.transform.localScale = new Vector3(canopyRadius * 2.2f, 1.6f, canopyRadius * 2.2f);
            DestroyImmediate(canopy1.GetComponent<Collider>());
            canopy1.GetComponent<Renderer>().sharedMaterial = canopyMaterialLush;

            GameObject canopy2 = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            canopy2.name = "Canopy_Crown";
            canopy2.transform.parent = tree.transform;
            canopy2.transform.localPosition = new Vector3(0f, trunkHeight + 2.1f, 0f);
            canopy2.transform.localScale = new Vector3(canopyRadius * 1.6f, 1.4f, canopyRadius * 1.6f);
            DestroyImmediate(canopy2.GetComponent<Collider>());
            canopy2.GetComponent<Renderer>().sharedMaterial = canopyMaterialGolden;
        }
        else if (typology == 1)
        {
            // Typology 1: Coastal Royal Palm
            // Under-canopy clearance: 4.8m (ground completely open and clear)
            float trunkRadius = 0.16f;
            float trunkHeight = 4.8f;

            // Slender trunk
            GameObject trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.name = "Trunk";
            trunk.transform.parent = tree.transform;
            trunk.transform.localPosition = new Vector3(0f, trunkHeight * 0.5f, 0f);
            trunk.transform.localScale = new Vector3(trunkRadius * 2f, trunkHeight * 0.5f, trunkRadius * 2f);
            DestroyImmediate(trunk.GetComponent<Collider>());
            trunk.GetComponent<Renderer>().sharedMaterial = trunkMaterial;

            // Palm frond crown
            GameObject crown = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            crown.name = "PalmCrown";
            crown.transform.parent = tree.transform;
            crown.transform.localPosition = new Vector3(0f, trunkHeight + 0.6f, 0f);
            crown.transform.localScale = new Vector3(3.2f, 0.9f, 3.2f);
            DestroyImmediate(crown.GetComponent<Collider>());
            crown.GetComponent<Renderer>().sharedMaterial = canopyMaterialGolden;
        }
        else
        {
            // Typology 2: Columnar Ashoka / Mast Tree
            // Under-canopy clearance: 2.2m
            float trunkRadius = 0.18f;
            float trunkHeight = 2.2f;

            // Trunk
            GameObject trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.name = "Trunk";
            trunk.transform.parent = tree.transform;
            trunk.transform.localPosition = new Vector3(0f, trunkHeight * 0.5f, 0f);
            trunk.transform.localScale = new Vector3(trunkRadius * 2f, trunkHeight * 0.5f, trunkRadius * 2f);
            DestroyImmediate(trunk.GetComponent<Collider>());
            trunk.GetComponent<Renderer>().sharedMaterial = trunkMaterial;

            // Columnar foliage
            GameObject colCanopy = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            colCanopy.name = "ColumnarCanopy";
            colCanopy.transform.parent = tree.transform;
            colCanopy.transform.localPosition = new Vector3(0f, trunkHeight + 1.9f, 0f);
            colCanopy.transform.localScale = new Vector3(1.7f, 1.9f, 1.7f);
            DestroyImmediate(colCanopy.GetComponent<Collider>());
            colCanopy.GetComponent<Renderer>().sharedMaterial = canopyMaterialLush;
        }

        return tree;
    }

    private Vector2 SamplePointAlongShape(Point2D[] shape, float targetDist, out Vector2 forwardDir)
    {
        forwardDir = Vector2.up;
        float accumulated = 0f;
        for (int i = 0; i < shape.Length - 1; i++)
        {
            Vector2 a = new Vector2(shape[i].x, shape[i].y);
            Vector2 b = new Vector2(shape[i+1].x, shape[i+1].y);
            float segLen = Vector2.Distance(a, b);
            if (accumulated + segLen >= targetDist || i == shape.Length - 2)
            {
                float t = segLen > 0.001f ? (targetDist - accumulated) / segLen : 0f;
                forwardDir = (b - a).normalized;
                return Vector2.Lerp(a, b, Mathf.Clamp01(t));
            }
            accumulated += segLen;
        }
        return new Vector2(shape[0].x, shape[0].y);
    }

    private float DistancePointToSegment(Vector2 p, Vector2 a, Vector2 b)
    {
        Vector2 ab = b - a;
        float l2 = ab.sqrMagnitude;
        if (l2 < 0.0001f) return Vector2.Distance(p, a);
        float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / l2);
        Vector2 proj = a + t * ab;
        return Vector2.Distance(p, proj);
    }

    private struct Bounds2D
    {
        public float minX, minZ, maxX, maxZ;
        public Bounds2D(float minX, float minZ, float maxX, float maxZ)
        {
            this.minX = minX;
            this.minZ = minZ;
            this.maxX = maxX;
            this.maxZ = maxZ;
        }
        public bool Contains(float x, float z)
        {
            return x >= minX && x <= maxX && z >= minZ && z <= maxZ;
        }
    }

    private struct RoadSegmentSimple
    {
        public Vector2 p1, p2;
        public float halfWidth;
    }
}
