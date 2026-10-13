using UnityEngine;
using System.IO;
using System.Collections.Generic;

public class HospitalVisualizer : MonoBehaviour
{
    public string jsonFileName = "RoadNetwork.json";

    private bool hasRendered;

    private struct RoadSegment
    {
        public Vector2 p1;
        public Vector2 p2;
    }

    void Start()
    {
        if (hasRendered) return;
        hasRendered = true;
        LoadAndCreateHospitals();
    }
    
    void LoadAndCreateHospitals()
    {
        string filePath = Path.Combine(Application.dataPath, "Generated", jsonFileName);
        
        if (!File.Exists(filePath))
        {
            Debug.LogWarning("RoadNetwork.json not found, cannot load hospitals.");
            return;
        }

        string jsonContent = File.ReadAllText(filePath);
        RoadNetworkData networkData = JsonUtility.FromJson<RoadNetworkData>(jsonContent);

        if (networkData != null && networkData.hospitals != null)
        {
            // Extract road segments to calculate entrance-facing orientation
            List<RoadSegment> roadSegments = new List<RoadSegment>();
            if (networkData.edges != null)
            {
                foreach (var edge in networkData.edges)
                {
                    if (edge.lanes == null) continue;
                    foreach (var lane in edge.lanes)
                    {
                        if (lane.shape == null || lane.shape.Length < 2) continue;
                        for (int i = 0; i < lane.shape.Length - 1; i++)
                        {
                            roadSegments.Add(new RoadSegment
                            {
                                p1 = new Vector2(lane.shape[i].x, lane.shape[i].y),
                                p2 = new Vector2(lane.shape[i+1].x, lane.shape[i+1].y)
                            });
                        }
                    }
                }
            }

            GameObject generatedHospitals = new GameObject("GeneratedHospitals");
            generatedHospitals.transform.SetParent(transform, false);

            foreach (var hosp in networkData.hospitals)
            {
                float facingAngle = 0f;
                if (roadSegments.Count > 0)
                {
                    Vector2 hPos = new Vector2(hosp.x, hosp.y);
                    float minDst = float.MaxValue;
                    Vector2 bestProj = hPos;

                    foreach (var seg in roadSegments)
                    {
                        Vector2 d = seg.p2 - seg.p1;
                        float l2 = d.sqrMagnitude;
                        float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(hPos - seg.p1, d) / l2) : 0f;
                        Vector2 proj = seg.p1 + t * d;
                        float dist = Vector2.Distance(hPos, proj);
                        if (dist < minDst)
                        {
                            minDst = dist;
                            bestProj = proj;
                        }
                    }

                    Vector2 toRoad = bestProj - hPos;
                    if (toRoad.sqrMagnitude > 0.01f)
                    {
                        facingAngle = Mathf.Atan2(toRoad.x, toRoad.y) * Mathf.Rad2Deg;
                    }
                }

                CreateHospitalModel(generatedHospitals.transform, hosp.id, hosp.name, hosp.x, hosp.y, facingAngle);
            }
            Debug.Log($"Successfully rendered {networkData.hospitals.Length} entrance-aligned hospital landmarks.");
        }
    }
    
    void CreateHospitalModel(Transform parent, string id, string name, float sumoX, float sumoY, float facingAngle)
    {
        Vector3 position = new Vector3(sumoX, 0f, sumoY);
        
        GameObject hospital = new GameObject("Hospital_" + id);
        hospital.transform.parent = parent;
        hospital.transform.localPosition = position;
        hospital.transform.localRotation = Quaternion.Euler(0f, facingAngle, 0f);
        hospital.isStatic = true;

        // Shared materials
        Shader litShader = Shader.Find("Universal Render Pipeline/Lit");
        if (litShader == null) litShader = Shader.Find("Standard");

        Shader unlitShader = Shader.Find("Universal Render Pipeline/Unlit");
        if (unlitShader == null) unlitShader = Shader.Find("Unlit/Color");

        Material whiteExteriorMat = new Material(litShader);
        Color whiteCol = new Color(0.68f, 0.72f, 0.76f);
        whiteExteriorMat.color = whiteCol;
        if (whiteExteriorMat.HasProperty("_BaseColor")) whiteExteriorMat.SetColor("_BaseColor", whiteCol);
        if (whiteExteriorMat.HasProperty("_Smoothness")) whiteExteriorMat.SetFloat("_Smoothness", 0.15f);

        Material accentCanopyMat = new Material(litShader);
        Color canopyCol = new Color(0.18f, 0.26f, 0.36f);
        accentCanopyMat.color = canopyCol;
        if (accentCanopyMat.HasProperty("_BaseColor")) accentCanopyMat.SetColor("_BaseColor", canopyCol);

        Material redCrossMat = new Material(unlitShader);
        Color redCol = new Color(1.0f, 0.12f, 0.12f);
        redCrossMat.color = redCol;
        if (redCrossMat.HasProperty("_BaseColor")) redCrossMat.SetColor("_BaseColor", redCol);

        Material signboardBackMat = new Material(litShader);
        Color signBackCol = new Color(0.10f, 0.12f, 0.18f);
        signboardBackMat.color = signBackCol;
        if (signboardBackMat.HasProperty("_BaseColor")) signboardBackMat.SetColor("_BaseColor", signBackCol);

        // 1. Main Hospital Wing (Central Tower) - ground contact at Y = 0
        GameObject mainBlock = GameObject.CreatePrimitive(PrimitiveType.Cube);
        mainBlock.name = "MainTower";
        mainBlock.transform.parent = hospital.transform;
        mainBlock.transform.localPosition = new Vector3(0f, 8.0f, 0f); // 16m tall, centered at 8m
        mainBlock.transform.localRotation = Quaternion.identity;
        mainBlock.transform.localScale = new Vector3(26f, 16f, 18f);
        Destroy(mainBlock.GetComponent<Collider>());
        mainBlock.GetComponent<Renderer>().material = whiteExteriorMat;

        // 2. Lateral Inpatient Wings
        GameObject sideWings = GameObject.CreatePrimitive(PrimitiveType.Cube);
        sideWings.name = "SideWings";
        sideWings.transform.parent = hospital.transform;
        sideWings.transform.localPosition = new Vector3(0f, 4.75f, -2.0f); // 9.5m tall, centered at 4.75m
        sideWings.transform.localRotation = Quaternion.identity;
        sideWings.transform.localScale = new Vector3(42f, 9.5f, 14f);
        Destroy(sideWings.GetComponent<Collider>());
        sideWings.GetComponent<Renderer>().material = whiteExteriorMat;

        // 3. Emergency / Entrance Canopy facing road (+Z)
        GameObject canopy = GameObject.CreatePrimitive(PrimitiveType.Cube);
        canopy.name = "EntranceCanopy";
        canopy.transform.parent = hospital.transform;
        canopy.transform.localPosition = new Vector3(0f, 4.5f, 12.0f);
        canopy.transform.localRotation = Quaternion.identity;
        canopy.transform.localScale = new Vector3(16f, 1.0f, 7.0f);
        Destroy(canopy.GetComponent<Collider>());
        canopy.GetComponent<Renderer>().material = accentCanopyMat;

        // Canopy support pillars
        for (int p = -1; p <= 1; p += 2)
        {
            GameObject pillar = GameObject.CreatePrimitive(PrimitiveType.Cube);
            pillar.name = "CanopyPillar_" + (p > 0 ? "R" : "L");
            pillar.transform.parent = hospital.transform;
            pillar.transform.localPosition = new Vector3(p * 6.8f, 2.0f, 14.5f);
            pillar.transform.localRotation = Quaternion.identity;
            pillar.transform.localScale = new Vector3(0.6f, 4.0f, 0.6f);
            Destroy(pillar.GetComponent<Collider>());
            pillar.GetComponent<Renderer>().material = whiteExteriorMat;
        }

        // 4. Red Emergency Facade Band
        GameObject redBand = GameObject.CreatePrimitive(PrimitiveType.Cube);
        redBand.name = "EmergencyBand";
        redBand.transform.parent = hospital.transform;
        redBand.transform.localPosition = new Vector3(0f, 9.8f, 0f);
        redBand.transform.localRotation = Quaternion.identity;
        redBand.transform.localScale = new Vector3(26.2f, 0.6f, 18.2f);
        Destroy(redBand.GetComponent<Collider>());
        redBand.GetComponent<Renderer>().material = redCrossMat;

        // 5. Medical Crosses (Emissive Red)
        // Roof cross visible from overhead / aerial camera
        CreateCross(hospital.transform, new Vector3(0f, 18.5f, 0f), Vector3.forward, redCrossMat, 4.8f);
        // Entrance cross facing oncoming traffic on the access road (+Z)
        CreateCross(hospital.transform, new Vector3(0f, 6.8f, 9.1f), Vector3.forward, redCrossMat, 2.6f);

        // 6. Readable Illuminated 3D Signboard
        string displayName = string.IsNullOrEmpty(name) ? id.Replace("_", " ").ToUpper() : name.ToUpper();

        GameObject signBackplate = GameObject.CreatePrimitive(PrimitiveType.Cube);
        signBackplate.name = "SignboardBackplate";
        signBackplate.transform.parent = hospital.transform;
        signBackplate.transform.localPosition = new Vector3(0f, 18.8f, 0f);
        signBackplate.transform.localRotation = Quaternion.identity;
        signBackplate.transform.localScale = new Vector3(18f, 3.2f, 0.4f);
        Destroy(signBackplate.GetComponent<Collider>());
        signBackplate.GetComponent<Renderer>().material = signboardBackMat;

        // TextMesh Sign
        GameObject signTextObj = new GameObject("SignboardText");
        signTextObj.transform.parent = signBackplate.transform;
        signTextObj.transform.localPosition = new Vector3(0f, 0f, 0.6f);
        signTextObj.transform.localRotation = Quaternion.identity;

        TextMesh tm = signTextObj.AddComponent<TextMesh>();
        tm.text = displayName;
        tm.characterSize = 0.22f;
        tm.fontSize = 64;
        tm.fontStyle = FontStyle.Bold;
        tm.anchor = TextAnchor.MiddleCenter;
        tm.alignment = TextAlignment.Center;
        tm.color = Color.white;

        // Shadow text for high-contrast crispness
        GameObject shadowTextObj = new GameObject("ShadowText");
        shadowTextObj.transform.parent = signBackplate.transform;
        shadowTextObj.transform.localPosition = new Vector3(0.04f, -0.04f, 0.55f);
        shadowTextObj.transform.localRotation = Quaternion.identity;

        TextMesh s_tm = shadowTextObj.AddComponent<TextMesh>();
        s_tm.text = displayName;
        s_tm.characterSize = 0.22f;
        s_tm.fontSize = 64;
        s_tm.fontStyle = FontStyle.Bold;
        s_tm.anchor = TextAnchor.MiddleCenter;
        s_tm.alignment = TextAlignment.Center;
        s_tm.color = Color.black;
    }
    
    private void CreateCross(Transform parent, Vector3 localPosition, Vector3 forward, Material mat, float scale)
    {
        GameObject crossRoot = new GameObject("MedicalCross");
        crossRoot.transform.parent = parent;
        crossRoot.transform.localPosition = localPosition;
        crossRoot.transform.localRotation = Quaternion.LookRotation(forward);

        GameObject vBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        vBar.name = "VBar";
        vBar.transform.parent = crossRoot.transform;
        vBar.transform.localPosition = Vector3.zero;
        vBar.transform.localRotation = Quaternion.identity;
        vBar.transform.localScale = new Vector3(scale * 0.32f, scale, scale * 0.12f);
        Destroy(vBar.GetComponent<Collider>());
        vBar.GetComponent<Renderer>().material = mat;
        
        GameObject hBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        hBar.name = "HBar";
        hBar.transform.parent = crossRoot.transform;
        hBar.transform.localPosition = Vector3.zero;
        hBar.transform.localRotation = Quaternion.identity;
        hBar.transform.localScale = new Vector3(scale, scale * 0.32f, scale * 0.12f);
        Destroy(hBar.GetComponent<Collider>());
        hBar.GetComponent<Renderer>().material = mat;
    }
}
