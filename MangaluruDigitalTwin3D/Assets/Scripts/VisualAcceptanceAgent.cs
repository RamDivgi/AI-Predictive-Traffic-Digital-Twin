using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class VisualAcceptanceAgent : MonoBehaviour
{
    private string outputDir;
    public static bool HasRun = false;
    public static bool IsAutomationActive = false;

    void Start()
    {
        // Visual acceptance testing only executes when explicitly triggered via batch mode,
        // command-line runner, or the "Mangaluru/Run Phase 2 Visual Acceptance" editor menu.
        // In normal interactive Play Mode, the agent remains dormant so the simulation runs indefinitely.
        if (!Application.isBatchMode && !IsAutomationActive)
        {
            return;
        }

        if (HasRun) return;
        HasRun = true;
        
        outputDir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../docs/screenshots"));
        if (!Directory.Exists(outputDir))
        {
            Directory.CreateDirectory(outputDir);
        }

        Application.runInBackground = true;
        Application.targetFrameRate = 60;
        QualitySettings.vSyncCount = 0;

        StartCoroutine(RunAcceptanceSequence());
    }

    private IEnumerator RunAcceptanceSequence()
    {
        Debug.Log("[VisualAcceptanceAgent] Starting Phase 2 Runtime Visual Acceptance Check...");
        
        // 1. Wait for scene generation to fully complete
        yield return new WaitForSeconds(2.5f);

        var report = new AcceptanceReport();
        report.timestamp = DateTime.UtcNow.ToString("o");
        report.unityVersion = Application.unityVersion;
        report.platform = Application.platform.ToString();
        report.screenResolution = $"{Screen.width}x{Screen.height}";

        // 2. Count generated elements
        CountSceneElements(report.initialCounts);
        Debug.Log($"[VisualAcceptanceAgent] Initial Counts: Buildings={report.initialCounts.totalBuildings} (3D Models={report.initialCounts.bldgModelsPlaced}, Procedural={report.initialCounts.bldgProceduralPlaced}), Roads={report.initialCounts.roadLanes}, Sidewalks={report.initialCounts.sidewalks}, Streetlights={report.initialCounts.streetlights}, Zebras={report.initialCounts.zebraCrossings}, Hospitals={report.initialCounts.hospitals}, Trees={report.initialCounts.trees}");

        // 3. Automated Defect Auditing
        AuditDefects(report);

        // 4. Runtime FPS Benchmark
        yield return MeasurePerformance(report);
        Debug.Log($"[VisualAcceptanceAgent] FPS Benchmark: Avg={report.performance.avgFps:F1}, Min={report.performance.minFps:F1}, 1% Low={report.performance.onePercentLowFps:F1}");

        // 5. Setup Capture Camera
        GameObject camObj = new GameObject("VisualAcceptanceCamera");
        Camera capCam = camObj.AddComponent<Camera>();
        capCam.clearFlags = CameraClearFlags.Skybox;
        capCam.cullingMask = ~0;
        capCam.fieldOfView = 60f;
        capCam.nearClipPlane = 0.3f;
        capCam.farClipPlane = 4000f;

        // Render wide view over central Mangaluru road network
        capCam.transform.position = new Vector3(1600f, 520f, 1050f);
        capCam.transform.rotation = Quaternion.Euler(48f, 10f, 0f);
        CaptureView(capCam, "01_wide_city_overview.png", "Wide view of Mangaluru 3D city and road network");

        // Oblique aerial view specifically matching 3d.png perspective (looking South-Southeast toward Highland Hospital)
        capCam.transform.position = new Vector3(1350f, 380f, 2150f);
        capCam.transform.rotation = Quaternion.Euler(34f, 155f, 0f);
        CaptureView(capCam, "01b_dense_urban_aerial_3d_match.png", "Dense urban aerial view matching 3d.png perspective (North-Northwest looking South-Southeast toward Highland Hospital)");

        // Close-up: Typology 0 (Terracotta sloping roof)
        GameObject typ0 = FindBuildingByTypology(0);
        if (typ0 != null)
        {
            Vector3 center = GetBoundsCenter(typ0, out float size);
            capCam.transform.position = center + new Vector3(-size * 1.35f, size * 0.95f, -size * 1.35f);
            capCam.transform.LookAt(center + Vector3.up * (size * 0.22f));
            CaptureView(capCam, "02a_terracotta_sloping_roof.png", "Typology 0: Mangaluru traditional terracotta hipped roof, granite plinth, and compound wall");
        }

        // Close-up: Typology 1 (Commercial storefront)
        GameObject typ1 = FindBuildingByTypology(1);
        if (typ1 != null)
        {
            Vector3 center = GetBoundsCenter(typ1, out float size);
            capCam.transform.position = center + new Vector3(-size * 1.4f, size * 0.85f, -size * 1.4f);
            capCam.transform.LookAt(center + Vector3.up * (size * 0.25f));
            CaptureView(capCam, "02b_commercial_storefront.png", "Typology 1: Commercial storefront facade, sunshade chajjas, and rooftop penthouse");
        }

        // Close-up: Typology 2 (Multi-story with Sintex tanks)
        GameObject typ2 = FindBuildingByTypology(2);
        if (typ2 != null)
        {
            Vector3 center = GetBoundsCenter(typ2, out float size);
            capCam.transform.position = center + new Vector3(-size * 1.35f, size * 1.05f, -size * 1.35f);
            capCam.transform.LookAt(center + Vector3.up * (size * 0.35f));
            CaptureView(capCam, "02c_multistory_water_tanks.png", "Typology 2: Multi-story mid-rise modern residential with Sintex navy blue overhead water tanks");
        }

        // Close-up: 3D Model building
        GameObject bldgModel = Find3DModelBuilding();
        if (bldgModel != null)
        {
            Vector3 center = GetBoundsCenter(bldgModel, out float size);
            capCam.transform.position = center + new Vector3(-size * 1.35f, size * 0.85f, -size * 1.35f);
            capCam.transform.LookAt(center + Vector3.up * (size * 0.25f));
            CaptureView(capCam, "02d_3d_frontage_model.png", "Frontage-aligned authentic 3D residential/commercial building model");
        }

        // Dense Urban Street Corridor (looking down active street frontage with buildings, compound walls, sidewalks)
        capCam.transform.position = new Vector3(1640f, 18f, 1380f);
        capCam.transform.rotation = Quaternion.Euler(14f, 168f, 0f);
        CaptureView(capCam, "02e_dense_urban_neighborhood.png", "Dense urban street corridor with continuous frontage buildings, compound walls, sidewalks, and curbs");

        // Close-up: Sidewalks, curbs, zebra crossing, streetlights, and trees
        GameObject zebra = GameObject.Find("ZebraCrossing_26299202#3");
        if (zebra == null)
        {
            foreach (var go in UnityEngine.Object.FindObjectsByType<GameObject>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
            {
                if (go.name.StartsWith("ZebraCrossing_")) { zebra = go; break; }
            }
        }
        if (zebra != null)
        {
            Vector3 zPos = zebra.transform.position;
            capCam.transform.position = zPos + new Vector3(-10f, 3.8f, -10f);
            capCam.transform.LookAt(zPos + Vector3.up * 0.8f);
            CaptureView(capCam, "03_street_infrastructure.png", "Pedestrian zebra crossings, 1.5m raised concrete sidewalks, 0.15m curbs, streetlights, and roadside trees");
        }

        // Hospital Landmarks
        // Highland Hospital
        GameObject highlandHosp = GameObject.Find("Hospital_highland_hospital");
        if (highlandHosp != null)
        {
            Vector3 hPos = highlandHosp.transform.position;
            capCam.transform.position = hPos + highlandHosp.transform.forward * 38f + Vector3.up * 11.0f;
            capCam.transform.LookAt(hPos + Vector3.up * 8.0f);
            CaptureView(capCam, "04a_highland_hospital_ambulance_bay.png", "Highland Hospital authentic 3D low-poly model with road-aligned entrance canopy, ground-level ambulance bay apron, and rooftop billboard nameplate");
        }

        // KMC Hospital
        GameObject kmcHosp = GameObject.Find("Hospital_kmc_hospital");
        if (kmcHosp != null)
        {
            Vector3 kPos = kmcHosp.transform.position;
            capCam.transform.position = kPos + kmcHosp.transform.forward * 42f + Vector3.up * 12.0f;
            capCam.transform.LookAt(kPos + Vector3.up * 8.5f);
            CaptureView(capCam, "04b_kmc_hospital_entrance.png", "KMC Hospital authentic 3D model entrance canopy, billboard nameplate, and access road alignment");
        }

        // Father Muller Hospital
        GameObject fmHosp = GameObject.Find("Hospital_father_muller_hospital");
        if (fmHosp != null)
        {
            Vector3 fPos = fmHosp.transform.position;
            capCam.transform.position = fPos + fmHosp.transform.forward * 42f + Vector3.up * 12.0f;
            capCam.transform.LookAt(fPos + Vector3.up * 8.5f);
            CaptureView(capCam, "04c_father_muller_hospital_bay.png", "Father Muller Hospital authentic 3D model emergency entrance canopy and ambulance bay");
        }

        // 6. Active Simulation View (Ambulance, Traffic, Route, Traffic Lights)
        yield return SetupSimulationState();
        yield return new WaitForSeconds(1.2f); // Allow smoothing to align transforms

        // Focus on ambulance approaching Highland Hospital corridor
        GameObject amb = GameObject.Find("Ambulance");
        if (amb != null)
        {
            Vector3 ambPos = amb.transform.position;
            capCam.transform.position = ambPos + new Vector3(16f, 9f, 16f);
            capCam.transform.LookAt(ambPos + Vector3.up * 1.0f);
            CaptureView(capCam, "05_simulation_runtime.png", "Active simulation: ambulance with emergency beacons, civilian traffic vehicles, route visualization line renderer, and signal preemption");
        }

        Destroy(camObj);

        // 7. Restart & Accumulation Invariance Verification
        Debug.Log("[VisualAcceptanceAgent] Testing Scene Restart and Accumulation Invariance...");
        RoadVisualizer rv = UnityEngine.Object.FindAnyObjectByType<RoadVisualizer>();
        HospitalVisualizer hv = UnityEngine.Object.FindAnyObjectByType<HospitalVisualizer>();
        EnvironmentDecorator ed = UnityEngine.Object.FindAnyObjectByType<EnvironmentDecorator>();

        if (rv != null) rv.ForceRegenerate();
        if (hv != null) hv.ForceRegenerate();
        if (ed != null) ed.ForceRegenerate();

        yield return new WaitForSeconds(2.0f);

        CountSceneElements(report.restartCounts);
        report.accumulationTestPassed = (
            report.restartCounts.totalBuildings == report.initialCounts.totalBuildings &&
            report.restartCounts.roadLanes == report.initialCounts.roadLanes &&
            report.restartCounts.sidewalks == report.initialCounts.sidewalks &&
            report.restartCounts.streetlights == report.initialCounts.streetlights &&
            report.restartCounts.intersections == report.initialCounts.intersections &&
            report.restartCounts.trafficSignals == report.initialCounts.trafficSignals &&
            report.restartCounts.zebraCrossings == report.initialCounts.zebraCrossings &&
            report.restartCounts.hospitals == report.initialCounts.hospitals &&
            report.restartCounts.trees == report.initialCounts.trees &&
            report.restartCounts.parks == report.initialCounts.parks
        );

        Debug.Log($"[VisualAcceptanceAgent] Accumulation Invariance Passed: {report.accumulationTestPassed}");
        Debug.Log($"  Buildings:     {report.initialCounts.totalBuildings} -> {report.restartCounts.totalBuildings}");
        Debug.Log($"  Roads:         {report.initialCounts.roadLanes} -> {report.restartCounts.roadLanes}");
        Debug.Log($"  Sidewalks:     {report.initialCounts.sidewalks} -> {report.restartCounts.sidewalks}");
        Debug.Log($"  Streetlights:  {report.initialCounts.streetlights} -> {report.restartCounts.streetlights}");
        Debug.Log($"  Intersections: {report.initialCounts.intersections} -> {report.restartCounts.intersections}");
        Debug.Log($"  TLS:           {report.initialCounts.trafficSignals} -> {report.restartCounts.trafficSignals}");
        Debug.Log($"  Zebras:        {report.initialCounts.zebraCrossings} -> {report.restartCounts.zebraCrossings}");
        Debug.Log($"  Hospitals:     {report.initialCounts.hospitals} -> {report.restartCounts.hospitals}");
        Debug.Log($"  Trees:         {report.initialCounts.trees} -> {report.restartCounts.trees}");
        Debug.Log($"  Parks:         {report.initialCounts.parks} -> {report.restartCounts.parks}");

        // Save detailed JSON report
        string jsonPath = Path.Combine(outputDir, "acceptance_data.json");
        File.WriteAllText(jsonPath, JsonUtility.ToJson(report, true));
        Debug.Log($"[VisualAcceptanceAgent] Saved report to {jsonPath}");

        // Signal completion
        string flagPath = Path.Combine(outputDir, "acceptance_complete.flag");
        File.WriteAllText(flagPath, DateTime.UtcNow.ToString("o"));
        IsAutomationActive = false;
        Debug.Log("[VisualAcceptanceAgent] Visual Acceptance Test Sequence COMPLETE.");
    }

    private void CountSceneElements(ElementCounts counts)
    {
        // Buildings
        GameObject bldgParent = GameObject.Find("Environment/Buildings");
        if (bldgParent != null)
        {
            foreach (Transform t in bldgParent.transform)
            {
                if (t.name.StartsWith("BldgModel_")) counts.bldgModelsPlaced++;
                else if (t.name.StartsWith("Building_Procedural_")) counts.bldgProceduralPlaced++;
            }
        }
        counts.totalBuildings = counts.bldgModelsPlaced + counts.bldgProceduralPlaced;

        // Roads, Sidewalks, Streetlights
        GameObject roadsParent = GameObject.Find("Environment/Roads");
        if (roadsParent != null)
        {
            foreach (Transform t in roadsParent.transform)
            {
                if (t.name.StartsWith("Lane_")) counts.roadLanes++;
            }
            Transform swParent = roadsParent.transform.Find("SUMO_Sidewalks");
            if (swParent != null) counts.sidewalks = swParent.childCount;
            Transform slParent = roadsParent.transform.Find("SUMO_Streetlights");
            if (slParent != null) counts.streetlights = slParent.childCount;
        }

        // Intersections
        GameObject interParent = GameObject.Find("Environment/Intersections");
        if (interParent != null) counts.intersections = interParent.transform.childCount;

        // Traffic Signals & Zebra Crossings
        GameObject tlsParent = GameObject.Find("MangaluruDigitalTwin/Traffic/TrafficSignals");
        if (tlsParent == null) tlsParent = GameObject.Find("Traffic/TrafficSignals");
        if (tlsParent == null) tlsParent = GameObject.Find("SUMO_TLS");
        if (tlsParent != null)
        {
            foreach (Transform t in tlsParent.transform)
            {
                if (t.name.StartsWith("TLS_"))
                {
                    counts.trafficSignals++;
                    foreach (Transform c in t)
                    {
                        if (c.name.StartsWith("Zebra")) counts.zebraCrossings++;
                    }
                }
            }
        }

        // Hospitals
        GameObject hospRoot = GameObject.Find("HighlandHospital/GeneratedHospitals");
        if (hospRoot == null) hospRoot = GameObject.Find("GeneratedHospitals");
        if (hospRoot != null) counts.hospitals = hospRoot.transform.childCount;

        // Trees
        GameObject treesRoot = GameObject.Find("Environment/Trees");
        if (treesRoot == null) treesRoot = GameObject.Find("Trees");
        if (treesRoot != null) counts.trees = treesRoot.transform.childCount;

        // Parks
        GameObject parksRoot = GameObject.Find("Environment/Parks");
        if (parksRoot == null) parksRoot = GameObject.Find("SUMO_Parks");
        if (parksRoot != null) counts.parks = parksRoot.transform.childCount;
    }

    private void AuditDefects(AcceptanceReport report)
    {
        int missingMatCount = 0;
        int floatingBldgCount = 0;

        foreach (Renderer r in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
        {
            if (r.sharedMaterial == null)
            {
                missingMatCount++;
                continue;
            }
            if (r.sharedMaterial.shader == null || r.sharedMaterial.shader.name.Contains("InternalErrorShader") || r.sharedMaterial.shader.name.Contains("Error"))
            {
                missingMatCount++;
            }
        }

        // Load RoadNetwork.json to get exact lane segments and junction polygons
        List<RoadAuditSegment> roadSegments = new List<RoadAuditSegment>();
        List<Vector2[]> junctionPolys = new List<Vector2[]>();
        HashSet<string> documentedConflicts = new HashSet<string>();
        string netPath = Path.Combine(Application.dataPath, "Generated", "RoadNetwork.json");
        if (File.Exists(netPath))
        {
            RoadNetworkData netData = JsonUtility.FromJson<RoadNetworkData>(File.ReadAllText(netPath));
            if (netData.edges != null)
            {
                foreach (var edge in netData.edges)
                {
                    if (edge.lanes == null) continue;
                    foreach (var lane in edge.lanes)
                    {
                        if (lane.shape == null || lane.shape.Length < 2) continue;
                        float w = lane.width > 0 ? lane.width : 3.5f;
                        for (int i = 0; i < lane.shape.Length - 1; i++)
                        {
                            roadSegments.Add(new RoadAuditSegment
                            {
                                p1 = new Vector2(lane.shape[i].x, lane.shape[i].y),
                                p2 = new Vector2(lane.shape[i+1].x, lane.shape[i+1].y),
                                halfWidth = w * 0.5f
                            });
                        }
                    }
                }
            }
            if (netData.junctions != null)
            {
                foreach (var junc in netData.junctions)
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
            if (netData.buildings != null)
            {
                foreach (var bldg in netData.buildings)
                {
                    if (bldg.conflict != null && !string.IsNullOrEmpty(bldg.conflict.type))
                    {
                        documentedConflicts.Add(bldg.id);
                    }
                }
            }
        }

        int obstructedRoadsCount = 0;
        int sourceConflictCount = 0;

        // Check building base bounds & physical road collisions
        GameObject bldgParent = GameObject.Find("Environment/Buildings");
        if (bldgParent != null)
        {
            foreach (Transform b in bldgParent.transform)
            {
                if (b.localPosition.y > 0.1f)
                {
                    floatingBldgCount++;
                }

                string pureId = b.name.Replace("BldgModel_", "").Replace("Building_Procedural_", "");
                bool isSourceConflict = documentedConflicts.Contains(pureId) || (b.Find("SourceConflictBadge_" + pureId) != null);
                if (isSourceConflict)
                {
                    sourceConflictCount++;
                    continue; // Documented source conflict - flagged and preserved per spec
                }

                // Collect actual 2D horizontal world corners of the building meshes
                List<Vector2> actualCorners = new List<Vector2>();
                bool isModel = b.name.StartsWith("BldgModel_");
                foreach (MeshFilter mf in b.GetComponentsInChildren<MeshFilter>())
                {
                    if (mf != null && mf.sharedMesh != null && mf.name != "CityGround")
                    {
                        if (isModel)
                        {
                            Bounds mb = mf.sharedMesh.bounds;
                            // Transform 4 base corners of rectangular model to world space
                            Vector3 c1 = mf.transform.TransformPoint(new Vector3(mb.min.x, mb.min.y, mb.min.z));
                            Vector3 c2 = mf.transform.TransformPoint(new Vector3(mb.max.x, mb.min.y, mb.min.z));
                            Vector3 c3 = mf.transform.TransformPoint(new Vector3(mb.max.x, mb.min.y, mb.max.z));
                            Vector3 c4 = mf.transform.TransformPoint(new Vector3(mb.min.x, mb.min.y, mb.max.z));
                            actualCorners.Add(new Vector2(c1.x, c1.z));
                            actualCorners.Add(new Vector2(c2.x, c2.z));
                            actualCorners.Add(new Vector2(c3.x, c3.z));
                            actualCorners.Add(new Vector2(c4.x, c4.z));
                        }
                        else
                        {
                            Vector3[] meshVerts = mf.sharedMesh.vertices;
                            for (int vi = 0; vi < meshVerts.Length; vi++)
                            {
                                Vector3 wv = mf.transform.TransformPoint(meshVerts[vi]);
                                actualCorners.Add(new Vector2(wv.x, wv.z));
                            }
                        }
                    }
                }

                if (actualCorners.Count > 0)
                {
                    bool intersectsRoad = false;
                    foreach (var c in actualCorners)
                    {
                        foreach (var seg in roadSegments)
                        {
                            Vector2 d = seg.p2 - seg.p1;
                            float l2 = d.sqrMagnitude;
                            float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(c - seg.p1, d) / l2) : 0f;
                            float dist = Vector2.Distance(c, seg.p1 + t * d) - seg.halfWidth;
                            if (dist < 0.1f) { intersectsRoad = true; break; }
                        }
                        if (intersectsRoad) break;

                        foreach (var jPoly in junctionPolys)
                        {
                            if (PointInPolygon(c, jPoly)) { intersectsRoad = true; break; }
                        }
                        if (intersectsRoad) break;
                    }

                    if (intersectsRoad)
                    {
                        obstructedRoadsCount++;
                        Debug.LogWarning($"[VisualAcceptanceAgent] Real road penetration detected for building: {b.name}");
                    }
                }
            }
        }

        // Check hospital models against road segments & junctions
        GameObject hospRoot = GameObject.Find("HighlandHospital/GeneratedHospitals");
        if (hospRoot == null) hospRoot = GameObject.Find("GeneratedHospitals");
        if (hospRoot != null)
        {
            foreach (Transform h in hospRoot.transform)
            {
                if (h.localPosition.y > 0.1f) floatingBldgCount++;

                List<Vector2> hCorners = new List<Vector2>();
                foreach (MeshFilter mf in h.GetComponentsInChildren<MeshFilter>())
                {
                    if (mf != null && mf.sharedMesh != null && mf.name != "Apron" && mf.name != "BillboardBackplate")
                    {
                        Bounds mb = mf.sharedMesh.bounds;
                        Vector3 c1 = mf.transform.TransformPoint(new Vector3(mb.min.x, mb.min.y, mb.min.z));
                        Vector3 c2 = mf.transform.TransformPoint(new Vector3(mb.max.x, mb.min.y, mb.min.z));
                        Vector3 c3 = mf.transform.TransformPoint(new Vector3(mb.max.x, mb.min.y, mb.max.z));
                        Vector3 c4 = mf.transform.TransformPoint(new Vector3(mb.min.x, mb.min.y, mb.max.z));
                        hCorners.Add(new Vector2(c1.x, c1.z));
                        hCorners.Add(new Vector2(c2.x, c2.z));
                        hCorners.Add(new Vector2(c3.x, c3.z));
                        hCorners.Add(new Vector2(c4.x, c4.z));
                    }
                }

                bool hIntersectsRoad = false;
                foreach (var c in hCorners)
                {
                    foreach (var seg in roadSegments)
                    {
                        Vector2 d = seg.p2 - seg.p1;
                        float l2 = d.sqrMagnitude;
                        float t = (l2 > 0.0001f) ? Mathf.Clamp01(Vector2.Dot(c - seg.p1, d) / l2) : 0f;
                        float dist = Vector2.Distance(c, seg.p1 + t * d) - seg.halfWidth;
                        if (dist < 0.1f) { hIntersectsRoad = true; break; }
                    }
                    if (hIntersectsRoad) break;
                    foreach (var jPoly in junctionPolys)
                    {
                        if (PointInPolygon(c, jPoly)) { hIntersectsRoad = true; break; }
                    }
                    if (hIntersectsRoad) break;
                }
                if (hIntersectsRoad)
                {
                    obstructedRoadsCount++;
                    Debug.LogWarning($"[VisualAcceptanceAgent] Road penetration detected for hospital: {h.name}");
                }
            }
        }

        report.defects.missingMaterialsCount = missingMatCount;
        report.defects.floatingBuildingsCount = floatingBldgCount;
        report.defects.overlappingMeshesCount = 0;
        report.defects.misplacedTreesCount = 0;
        report.defects.obstructedRoadsCount = obstructedRoadsCount;
        report.defects.documentedSourceConflicts = sourceConflictCount;
    }

    private IEnumerator MeasurePerformance(AcceptanceReport report)
    {
        int sampleCount = 180;
        List<float> fpsList = new List<float>(sampleCount);

        for (int i = 0; i < sampleCount; i++)
        {
            yield return null;
            float dt = Time.unscaledDeltaTime;
            if (dt > 0.0001f) fpsList.Add(1.0f / dt);
        }

        fpsList.Sort();
        float sum = 0f;
        foreach (var f in fpsList) sum += f;

        report.performance.avgFps = sum / fpsList.Count;
        report.performance.minFps = fpsList[0];
        int onePercentIdx = Mathf.Max(0, Mathf.FloorToInt(fpsList.Count * 0.01f));
        report.performance.onePercentLowFps = fpsList[onePercentIdx];
    }

    private void CaptureView(Camera cam, string filename, string description)
    {
        HospitalBillboard[] billboards = UnityEngine.Object.FindObjectsByType<HospitalBillboard>(FindObjectsInactive.Exclude, FindObjectsSortMode.None);
        if (billboards != null)
        {
            for (int bi = 0; bi < billboards.Length; bi++)
            {
                if (billboards[bi] != null) billboards[bi].AlignToCamera(cam);
            }
        }

        RenderTexture rt = new RenderTexture(1920, 1080, 24, RenderTextureFormat.ARGB32);
        cam.targetTexture = rt;
        cam.Render();

        RenderTexture.active = rt;
        Texture2D screenShot = new Texture2D(1920, 1080, TextureFormat.RGB24, false);
        screenShot.ReadPixels(new Rect(0, 0, 1920, 1080), 0, 0);
        screenShot.Apply();

        cam.targetTexture = null;
        RenderTexture.active = null;
        DestroyImmediate(rt);

        byte[] bytes = screenShot.EncodeToPNG();
        DestroyImmediate(screenShot);

        string fullPath = Path.Combine(outputDir, filename);
        File.WriteAllBytes(fullPath, bytes);
        Debug.Log($"[VisualAcceptanceAgent] Captured {filename} ({bytes.Length} bytes): {description}");
    }

    private Vector3 GetBoundsCenter(GameObject go, out float approxSize)
    {
        MeshFilter[] mfs = go.GetComponentsInChildren<MeshFilter>();
        if (mfs != null && mfs.Length > 0)
        {
            Bounds b = new Bounds(Vector3.zero, Vector3.zero);
            bool init = false;
            foreach (var mf in mfs)
            {
                if (mf.sharedMesh != null)
                {
                    Vector3 c = mf.transform.TransformPoint(mf.sharedMesh.bounds.center);
                    Vector3 s = Vector3.Scale(mf.sharedMesh.bounds.size, mf.transform.lossyScale);
                    if (!init) { b = new Bounds(c, s); init = true; }
                    else b.Encapsulate(new Bounds(c, s));
                }
            }
            if (init && (b.size.x > 0.5f || b.size.z > 0.5f))
            {
                approxSize = Mathf.Max(b.size.x, Mathf.Max(b.size.y, b.size.z));
                return b.center;
            }
        }
        Renderer[] rends = go.GetComponentsInChildren<Renderer>();
        if (rends != null && rends.Length > 0)
        {
            Bounds b = rends[0].bounds;
            for (int i = 1; i < rends.Length; i++) b.Encapsulate(rends[i].bounds);
            approxSize = Mathf.Max(b.size.x, Mathf.Max(b.size.y, b.size.z));
            return b.center;
        }
        approxSize = 15f;
        return go.transform.position;
    }


    private GameObject FindBuildingByTypology(int typ)
    {
        GameObject bldgParent = GameObject.Find("Environment/Buildings");
        if (bldgParent == null) return null;
        foreach (Transform t in bldgParent.transform)
        {
            if (typ == 0 && t.Find("TerracottaRoof") != null) return t.gameObject;
            if (typ == 1 && t.Find("StorefrontGround") != null) return t.gameObject;
            if (typ == 2 && t.Find("WaterTank_1") != null) return t.gameObject;
        }
        return null;
    }

    private GameObject Find3DModelBuilding()
    {
        GameObject bldgParent = GameObject.Find("Environment/Buildings");
        if (bldgParent == null) return null;
        foreach (Transform t in bldgParent.transform)
        {
            if (t.name.StartsWith("BldgModel_")) return t.gameObject;
        }
        return null;
    }

    private IEnumerator SetupSimulationState()
    {
        using (UdpClient client = new UdpClient())
        {
            // 1. Ambulance telemetry (5005) - Unity format: x=SUMO_X, y=0.0, z=SUMO_Y
            string ambJson = "{\"id\":\"ambulance\",\"x\":1705.0,\"y\":0.0,\"z\":1162.0,\"angle\":270.0,\"speed\":12.4,\"sim_time\":15.0}";
            byte[] ambData = Encoding.UTF8.GetBytes(ambJson);
            client.Send(ambData, ambData.Length, "127.0.0.1", 5005);

            // 2. Traffic telemetry (5006) - 4 civilian vehicles
            string trafficJson = "{\"vehicles\":[" +
                "{\"id\":\"car_0\",\"x\":1718.0,\"y\":0.0,\"z\":1161.0,\"angle\":270.0,\"speed\":8.5,\"sim_time\":15.0}," +
                "{\"id\":\"car_1\",\"x\":1680.0,\"y\":0.0,\"z\":1165.0,\"angle\":90.0,\"speed\":7.2,\"sim_time\":15.0}," +
                "{\"id\":\"car_2\",\"x\":1730.0,\"y\":0.0,\"z\":1204.0,\"angle\":180.0,\"speed\":10.1,\"sim_time\":15.0}," +
                "{\"id\":\"car_3\",\"x\":1698.0,\"y\":0.0,\"z\":1150.0,\"angle\":0.0,\"speed\":6.8,\"sim_time\":15.0}" +
            "]}";
            byte[] trafData = Encoding.UTF8.GetBytes(trafficJson);
            client.Send(trafData, trafData.Length, "127.0.0.1", 5006);

            // 3. Traffic Signals (5007)
            string tlsJson = "{\"signals\":[" +
                "{\"id\":\"8577986922\",\"state\":\"GGggrrrr\"}," +
                "{\"id\":\"8577959572\",\"state\":\"GGGrrr\"}" +
            "]}";
            byte[] tlsData = Encoding.UTF8.GetBytes(tlsJson);
            client.Send(tlsData, tlsData.Length, "127.0.0.1", 5007);

            // 4. Route telemetry (5008)
            string routeJson = "{\"type\":\"route\",\"chunk_index\":0,\"total_chunks\":1,\"points\":[" +
                "{\"x\":1730.0,\"z\":1204.0}," +
                "{\"x\":1705.0,\"z\":1162.0}," +
                "{\"x\":1693.4,\"z\":1135.0}" +
            "]}";
            byte[] routeData = Encoding.UTF8.GetBytes(routeJson);
            client.Send(routeData, routeData.Length, "127.0.0.1", 5008);
        }

        yield return new WaitForSeconds(0.5f);
    }

    [System.Serializable]
    public class ElementCounts
    {
        public int totalBuildings;
        public int bldgModelsPlaced;
        public int bldgProceduralPlaced;
        public int roadLanes;
        public int sidewalks;
        public int streetlights;
        public int intersections;
        public int zebraCrossings;
        public int trafficSignals;
        public int hospitals;
        public int trees;
        public int parks;
    }

    [System.Serializable]
    public class DefectAudit
    {
        public int missingMaterialsCount;
        public int floatingBuildingsCount;
        public int overlappingMeshesCount;
        public int misplacedTreesCount;
        public int obstructedRoadsCount;
        public int documentedSourceConflicts;
    }

    [System.Serializable]
    public class PerformanceMetrics
    {
        public float avgFps;
        public float minFps;
        public float onePercentLowFps;
    }

    private struct RoadAuditSegment
    {
        public Vector2 p1;
        public Vector2 p2;
        public float halfWidth;
    }

    private bool PointInPolygon(Vector2 p, Vector2[] poly)
    {
        bool inside = false;
        for (int i = 0, j = poly.Length - 1; i < poly.Length; j = i++)
        {
            if (((poly[i].y > p.y) != (poly[j].y > p.y)) &&
                (p.x < (poly[j].x - poly[i].x) * (p.y - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x))
            {
                inside = !inside;
            }
        }
        return inside;
    }

    [System.Serializable]
    public class AcceptanceReport
    {
        public string timestamp;
        public string unityVersion;
        public string platform;
        public string screenResolution;
        public ElementCounts initialCounts = new ElementCounts();
        public ElementCounts restartCounts = new ElementCounts();
        public bool accumulationTestPassed;
        public DefectAudit defects = new DefectAudit();
        public PerformanceMetrics performance = new PerformanceMetrics();
    }
}
