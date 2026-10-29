using UnityEngine;
using System.IO;
using System.Collections.Generic;

public class HospitalVisualizer : MonoBehaviour
{
    public string jsonFileName = "RoadNetwork.json";
    public GameObject hospitalPrefabOverride;

    private bool hasRendered;
    private GameObject hospitalPrefab;

    private struct RoadSegment
    {
        public Vector2 p1;
        public Vector2 p2;
        public float halfWidth;
    }

    void Start()
    {
        if (hasRendered) return;
        hasRendered = true;
        LoadAndCreateHospitals();
    }

    public void ForceRegenerate()
    {
        hasRendered = false;
        LoadAndCreateHospitals();
    }

    void LoadAndCreateHospitals()
    {
        string filePath = Path.Combine(Application.dataPath, "Generated", jsonFileName);
        
        if (!File.Exists(filePath))
        {
            Debug.LogWarning("[HospitalVisualizer] RoadNetwork.json not found, cannot load hospitals.");
            return;
        }

        string jsonContent = File.ReadAllText(filePath);
        RoadNetworkData networkData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);

        if (networkData == null || networkData.hospitals == null)
        {
            Debug.LogWarning("[HospitalVisualizer] No hospital data found in RoadNetwork.json.");
            return;
        }

        // Load HospitalPrefab
        if (hospitalPrefabOverride != null)
        {
            hospitalPrefab = hospitalPrefabOverride;
        }
        else
        {
            hospitalPrefab = Resources.Load<GameObject>("Hospital/HospitalPrefab");
        }

        if (hospitalPrefab == null)
        {
            Debug.LogError("[HospitalVisualizer] Could not load Hospital/HospitalPrefab from Resources!");
            return;
        }

        // Collect road segments to calculate entrance-facing orientation & road clearance
        List<RoadSegment> roadSegments = new List<RoadSegment>();
        if (networkData.edges != null)
        {
            foreach (var edge in networkData.edges)
            {
                if (edge.lanes == null) continue;
                foreach (var lane in edge.lanes)
                {
                    if (lane.shape == null || lane.shape.Length < 2) continue;
                    float w = lane.width > 0 ? lane.width : 3.5f;
                    for (int i = 0; i < lane.shape.Length - 1; i++)
                    {
                        roadSegments.Add(new RoadSegment
                        {
                            p1 = new Vector2(lane.shape[i].x, lane.shape[i].y),
                            p2 = new Vector2(lane.shape[i+1].x, lane.shape[i+1].y),
                            halfWidth = w * 0.5f
                        });
                    }
                }
            }
        }

        // Clean up any existing instances to avoid duplicates on scene reloads
        Transform existing = transform.Find("GeneratedHospitals");
        if (existing != null)
        {
            DestroyImmediate(existing.gameObject);
        }

        GameObject generatedHospitals = new GameObject("GeneratedHospitals");
        generatedHospitals.transform.SetParent(transform, false);

        int placedCount = 0;

        foreach (var hosp in networkData.hospitals)
        {
            Vector2 hPos = new Vector2(hosp.x, hosp.y);
            float facingAngle = 0f;
            float distToRoad = float.MaxValue;
            Vector2 toRoad = Vector2.up;

            if (roadSegments.Count > 0)
            {
                float minDst = float.MaxValue;
                Vector2 bestProj = hPos;

                foreach (var seg in roadSegments)
                {
                    Vector2 d = seg.p2 - seg.p1;
                    float l2 = d.sqrMagnitude;
                    float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(hPos - seg.p1, d) / l2) : 0f;
                    Vector2 proj = seg.p1 + t * d;
                    float dToEdge = Vector2.Distance(hPos, proj) - seg.halfWidth;
                    if (dToEdge < minDst)
                    {
                        minDst = dToEdge;
                        bestProj = proj;
                    }
                }

                distToRoad = minDst;
                Vector2 dir = bestProj - hPos;
                if (dir.sqrMagnitude > 0.01f)
                {
                    toRoad = dir.normalized;
                    facingAngle = Mathf.Atan2(toRoad.x, toRoad.y) * Mathf.Rad2Deg;
                }
            }

            // Calculate uniform scale preserving natural proportions (width=30m, depth=30m, height=15.5m)
            float scale = 0.88f; // Standard architectural scale for Mangaluru hospitals
            if (hosp.footprint_width > 0 && hosp.footprint_depth > 0)
            {
                float targetSpan = Mathf.Min(hosp.footprint_width, hosp.footprint_depth) * 0.85f;
                scale = Mathf.Clamp(targetSpan / 30.0f, 0.70f, 0.95f);
            }
            else if (distToRoad < 22.0f)
            {
                scale = Mathf.Clamp((distToRoad - 3.5f) / 16.0f, 0.68f, 0.85f);
            }

            // Ensure entrance canopy (+15m * scale along facingAngle) maintains >= 3.0m safety clearance to road
            Vector2 finalPos = hPos;
            float frontReach = 15.0f * scale;
            if (distToRoad < frontReach + 3.0f)
            {
                float setbackShift = (frontReach + 3.0f) - distToRoad;
                finalPos -= toRoad * setbackShift;
            }

            CreateHospitalInstance(generatedHospitals.transform, hosp, finalPos, facingAngle, scale);
            placedCount++;
        }

        Debug.Log($"[HospitalVisualizer] Successfully placed {placedCount} 3D hospital models with dynamic billboard nameplates.");
    }

    void CreateHospitalInstance(Transform parent, HospitalData hosp, Vector2 pos, float facingAngle, float scale)
    {
        Vector3 worldPos = new Vector3(pos.x, 0f, pos.y);

        GameObject hospRoot = new GameObject("Hospital_" + hosp.id);
        hospRoot.transform.SetParent(parent, false);
        hospRoot.transform.localPosition = worldPos;
        hospRoot.transform.localRotation = Quaternion.Euler(0f, facingAngle, 0f);
        hospRoot.isStatic = true;

        // Instantiate low-poly hospital prefab
        GameObject model = Instantiate(hospitalPrefab, hospRoot.transform);
        model.name = "HospitalModel";
        model.transform.localPosition = Vector3.zero;
        model.transform.localRotation = Quaternion.identity;
        model.transform.localScale = new Vector3(scale, scale, scale);

        // Remove any physics colliders so they don't block traffic or ambulances
        foreach (var col in model.GetComponentsInChildren<Collider>())
        {
            Destroy(col);
        }

        // Add Ground-Level Ambulance Bay Apron in front of the entrance canopy
        CreateAmbulanceBayApron(hospRoot.transform, scale);

        // Add Camera-Billboard Hospital Name Label above the roof
        float roofHeight = 15.46f * scale;
        CreateHospitalBillboardLabel(hospRoot.transform, hosp.id, hosp.name, roofHeight);
    }

    void CreateAmbulanceBayApron(Transform parent, float scale)
    {
        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");

        Material bayMat = new Material(unlitShader);
        Color apronCol = new Color(0.14f, 0.32f, 0.22f, 0.85f); // Subtle emerald emergency bay tint
        bayMat.color = apronCol;
        if (bayMat.HasProperty("_BaseColor")) bayMat.SetColor("_BaseColor", apronCol);

        GameObject apron = GameObject.CreatePrimitive(PrimitiveType.Quad);
        apron.name = "AmbulanceBayApron";
        apron.transform.SetParent(parent, false);
        // Positioned right in front of the entrance canopy on the ground plane (Y=0.03m to avoid z-fighting)
        apron.transform.localPosition = new Vector3(0f, 0.03f, 13.5f * scale);
        apron.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
        apron.transform.localScale = new Vector3(10f * scale, 6.5f * scale, 1f);
        Destroy(apron.GetComponent<Collider>());
        apron.GetComponent<Renderer>().material = bayMat;
    }

    void CreateHospitalBillboardLabel(Transform parent, string id, string name, float roofHeight)
    {
        string displayName = string.IsNullOrEmpty(name) ? id.Replace("_", " ").ToUpper() : name;

        // Label Root positioned safely above the rooftop
        GameObject labelRoot = new GameObject("HospitalLabel_" + id);
        labelRoot.transform.SetParent(parent, false);
        labelRoot.transform.localPosition = new Vector3(0f, roofHeight + 2.8f, 0f);

        // Attach HospitalBillboard component so it dynamically faces the camera
        labelRoot.AddComponent<HospitalBillboard>();

        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");

        Material backplateMat = new Material(unlitShader);
        Color backCol = new Color(0.06f, 0.08f, 0.12f, 0.92f); // Sleek dark charcoal slate
        backplateMat.color = backCol;
        if (backplateMat.HasProperty("_BaseColor")) backplateMat.SetColor("_BaseColor", backCol);

        Material crossMat = new Material(unlitShader);
        Color redCrossCol = new Color(0.95f, 0.15f, 0.15f, 1.0f); // Emissive emergency red
        crossMat.color = redCrossCol;
        if (crossMat.HasProperty("_BaseColor")) crossMat.SetColor("_BaseColor", redCrossCol);

        float plateWidth = Mathf.Clamp(displayName.Length * 0.55f + 4.2f, 10.0f, 18.0f);
        float plateHeight = 2.4f;

        // Dark Charcoal Slate Backplate (Solid 3D box: 0.35m thick, completely isolating front & rear faces)
        GameObject backplate = GameObject.CreatePrimitive(PrimitiveType.Cube);
        backplate.name = "SignBackplate";
        backplate.transform.SetParent(labelRoot.transform, false);
        backplate.transform.localPosition = Vector3.zero;
        backplate.transform.localRotation = Quaternion.identity;
        backplate.transform.localScale = new Vector3(plateWidth, plateHeight, 0.35f);
        Destroy(backplate.GetComponent<Collider>());
        backplate.GetComponent<Renderer>().material = backplateMat;

        float crossX = -plateWidth * 0.5f + 1.25f;

        // Front Face (-Z toward camera)
        CreateCrossIcon(labelRoot.transform, new Vector3(crossX, 0f, -0.20f), Quaternion.identity, crossMat, 1.35f);
        CreateSignText(labelRoot.transform, displayName, new Vector3(0.55f, 0f, -0.20f), Quaternion.identity);
    }

    void CreateSignText(Transform parent, string text, Vector3 localPos, Quaternion localRot)
    {
        GameObject textObj = new GameObject("Text");
        textObj.transform.SetParent(parent, false);
        textObj.transform.localPosition = localPos;
        textObj.transform.localRotation = localRot;

        TextMesh tm = textObj.AddComponent<TextMesh>();
        tm.text = text;
        tm.characterSize = 0.38f;
        tm.fontSize = 36;
        tm.fontStyle = FontStyle.Bold;
        tm.anchor = TextAnchor.MiddleCenter;
        tm.alignment = TextAlignment.Center;
        tm.color = Color.white;
    }

    void CreateCrossIcon(Transform parent, Vector3 localPos, Quaternion localRot, Material mat, float size)
    {
        GameObject cross = new GameObject("CrossIcon");
        cross.transform.SetParent(parent, false);
        cross.transform.localPosition = localPos;
        cross.transform.localRotation = localRot;

        GameObject vBar = GameObject.CreatePrimitive(PrimitiveType.Quad);
        vBar.name = "VBar";
        vBar.transform.SetParent(cross.transform, false);
        vBar.transform.localPosition = Vector3.zero;
        vBar.transform.localScale = new Vector3(size * 0.32f, size, 1f);
        Destroy(vBar.GetComponent<Collider>());
        vBar.GetComponent<Renderer>().material = mat;

        GameObject hBar = GameObject.CreatePrimitive(PrimitiveType.Quad);
        hBar.name = "HBar";
        hBar.transform.SetParent(cross.transform, false);
        hBar.transform.localPosition = new Vector3(0f, 0f, -0.005f);
        hBar.transform.localScale = new Vector3(size, size * 0.32f, 1f);
        Destroy(hBar.GetComponent<Collider>());
        hBar.GetComponent<Renderer>().material = mat;
    }
}
