using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class HospitalAssetProcessor
{
    static HospitalAssetProcessor()
    {
        EditorApplication.update += MonitorTrigger;
    }

    private static void MonitorTrigger()
    {
        string triggerPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../process_hospital.trigger"));
        if (File.Exists(triggerPath))
        {
            try { File.Delete(triggerPath); } catch {}
            ProcessHospitalAsset();
        }
    }

    [System.Serializable]
    public class MeshChildInfo
    {
        public string name;
        public string meshName;
        public int vertexCount;
        public int triangleCount;
        public string boundsMin;
        public string boundsMax;
        public string boundsSize;
        public List<string> materialNames = new List<string>();
    }

    [System.Serializable]
    public class HospitalModelInspection
    {
        public string assetPath;
        public float totalSizeX;
        public float totalSizeY;
        public float totalSizeZ;
        public float minX;
        public float maxX;
        public float minY;
        public float maxY;
        public float minZ;
        public float maxZ;
        public float pivotOffsetY; // How far below/above ground the pivot is
        public List<MeshChildInfo> children = new List<MeshChildInfo>();
        public List<string> texturePaths = new List<string>();
    }

    [MenuItem("Tools/Inspect and Setup Hospital Asset")]
    public static void ProcessHospitalAsset()
    {
        Debug.Log("[HospitalAssetProcessor] Starting hospital asset inspection and setup...");

        string fbxPath = "Assets/Models/Models/Buildings/Hospital/source/Hospital.fbx";
        GameObject fbxAsset = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
        if (fbxAsset == null)
        {
            Debug.LogError("[HospitalAssetProcessor] Failed to find Hospital.fbx at: " + fbxPath);
            return;
        }

        // Ensure materials folder exists
        string matFolder = "Assets/Models/Models/Buildings/Hospital/materials";
        if (!AssetDatabase.IsValidFolder(matFolder))
        {
            AssetDatabase.CreateFolder("Assets/Models/Models/Buildings/Hospital", "materials");
        }

        // Textures
        string tex1Path = "Assets/Models/Models/Buildings/Hospital/textures/lowpoly_tex-2.png";
        string tex2Path = "Assets/Models/Models/Buildings/Hospital/textures/names_and_details.png";
        Texture2D tex1 = AssetDatabase.LoadAssetAtPath<Texture2D>(tex1Path);
        Texture2D tex2 = AssetDatabase.LoadAssetAtPath<Texture2D>(tex2Path);

        // Configure texture import settings
        ConfigureTexture(tex1Path);
        ConfigureTexture(tex2Path);

        // Find URP Lit shader or standard fallback
        Shader litShader = Shader.Find("Universal Render Pipeline/Lit");
        if (litShader == null) litShader = Shader.Find("Standard");

        // Create or get materials
        Material mat1 = AssetDatabase.LoadAssetAtPath<Material>(matFolder + "/Hospital_Main.mat");
        if (mat1 == null)
        {
            mat1 = new Material(litShader);
            mat1.name = "Hospital_Main";
            if (tex1 != null)
            {
                mat1.mainTexture = tex1;
                if (mat1.HasProperty("_BaseMap")) mat1.SetTexture("_BaseMap", tex1);
                if (mat1.HasProperty("_BaseColor")) mat1.SetColor("_BaseColor", Color.white);
            }
            if (mat1.HasProperty("_Smoothness")) mat1.SetFloat("_Smoothness", 0.15f);
            AssetDatabase.CreateAsset(mat1, matFolder + "/Hospital_Main.mat");
        }

        Material mat2 = AssetDatabase.LoadAssetAtPath<Material>(matFolder + "/Hospital_Details.mat");
        if (mat2 == null)
        {
            mat2 = new Material(litShader);
            mat2.name = "Hospital_Details";
            if (tex2 != null)
            {
                mat2.mainTexture = tex2;
                if (mat2.HasProperty("_BaseMap")) mat2.SetTexture("_BaseMap", tex2);
                if (mat2.HasProperty("_BaseColor")) mat2.SetColor("_BaseColor", Color.white);
            }
            if (mat2.HasProperty("_Smoothness")) mat2.SetFloat("_Smoothness", 0.15f);
            AssetDatabase.CreateAsset(mat2, matFolder + "/Hospital_Details.mat");
        }

        // Instantiate FBX in a clean scene position to measure
        GameObject instance = Object.Instantiate(fbxAsset);
        instance.name = "Hospital_TempInstance";
        instance.transform.position = Vector3.zero;
        instance.transform.rotation = Quaternion.identity;
        instance.transform.localScale = Vector3.one;

        HospitalModelInspection inspection = new HospitalModelInspection();
        inspection.assetPath = fbxPath;
        if (tex1 != null) inspection.texturePaths.Add(tex1Path);
        if (tex2 != null) inspection.texturePaths.Add(tex2Path);

        Bounds combinedBounds = new Bounds();
        bool hasBounds = false;

        MeshFilter[] meshFilters = instance.GetComponentsInChildren<MeshFilter>();
        foreach (var mf in meshFilters)
        {
            if (mf.sharedMesh == null) continue;
            Mesh m = mf.sharedMesh;
            MeshRenderer mr = mf.GetComponent<MeshRenderer>();

            MeshChildInfo childInfo = new MeshChildInfo();
            childInfo.name = mf.gameObject.name;
            childInfo.meshName = m.name;
            childInfo.vertexCount = m.vertexCount;
            childInfo.triangleCount = m.triangles.Length / 3;

            Bounds meshBounds = m.bounds;
            Vector3 wMin = mf.transform.TransformPoint(meshBounds.min);
            Vector3 wMax = mf.transform.TransformPoint(meshBounds.max);
            Bounds worldB = new Bounds((wMin + wMax) * 0.5f, new Vector3(Mathf.Abs(wMax.x - wMin.x), Mathf.Abs(wMax.y - wMin.y), Mathf.Abs(wMax.z - wMin.z)));

            childInfo.boundsMin = worldB.min.ToString("F3");
            childInfo.boundsMax = worldB.max.ToString("F3");
            childInfo.boundsSize = worldB.size.ToString("F3");

            if (mr != null)
            {
                foreach (var mat in mr.sharedMaterials)
                {
                    if (mat != null) childInfo.materialNames.Add(mat.name);
                }

                // If materials were missing or dummy, assign our configured materials
                Material[] currentMats = mr.sharedMaterials;
                for (int i = 0; i < currentMats.Length; i++)
                {
                    if (currentMats[i] == null || currentMats[i].name.Contains("Default") || currentMats[i].mainTexture == null)
                    {
                        // Check if texture names match or assign main
                        if (currentMats[i] != null && currentMats[i].name.ToLower().Contains("detail"))
                        {
                            currentMats[i] = mat2;
                        }
                        else
                        {
                            currentMats[i] = mat1;
                        }
                    }
                }
                mr.sharedMaterials = currentMats;
            }

            if (!hasBounds)
            {
                combinedBounds = worldB;
                hasBounds = true;
            }
            else
            {
                combinedBounds.Encapsulate(worldB);
            }

            inspection.children.Add(childInfo);
        }

        inspection.totalSizeX = combinedBounds.size.x;
        inspection.totalSizeY = combinedBounds.size.y;
        inspection.totalSizeZ = combinedBounds.size.z;
        inspection.minX = combinedBounds.min.x;
        inspection.maxX = combinedBounds.max.x;
        inspection.minY = combinedBounds.min.y;
        inspection.maxY = combinedBounds.max.y;
        inspection.minZ = combinedBounds.min.z;
        inspection.maxZ = combinedBounds.max.z;
        inspection.pivotOffsetY = combinedBounds.min.y; // distance from pivot (0) to bottom

        Debug.Log($"[HospitalAssetProcessor] Measured Dimensions: Width(X)={inspection.totalSizeX:F2}m, Height(Y)={inspection.totalSizeY:F2}m, Depth(Z)={inspection.totalSizeZ:F2}m, MinY={inspection.minY:F2}m");

        // Ensure Resources/Hospital directory exists
        string resFolder = "Assets/Resources/Hospital";
        if (!AssetDatabase.IsValidFolder("Assets/Resources"))
        {
            AssetDatabase.CreateFolder("Assets", "Resources");
        }
        if (!AssetDatabase.IsValidFolder(resFolder))
        {
            AssetDatabase.CreateFolder("Assets/Resources", "Hospital");
        }

        // Create a root wrapper prefab so the pivot is cleanly at the center-bottom of the building
        GameObject rootWrapper = new GameObject("Hospital_Prefab");
        GameObject visualChild = Object.Instantiate(fbxAsset, rootWrapper.transform);
        visualChild.name = "Model";
        
        // Offset visual child so that Y=0 of the wrapper is precisely at the ground base (bottom) of the hospital
        visualChild.transform.localPosition = new Vector3(-combinedBounds.center.x, -combinedBounds.min.y, -combinedBounds.center.z);
        visualChild.transform.localRotation = Quaternion.identity;
        visualChild.transform.localScale = Vector3.one;

        // Apply materials to visualChild
        foreach (var mr in visualChild.GetComponentsInChildren<MeshRenderer>())
        {
            Material[] mats = mr.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                if (mats[i] != null && mats[i].name.ToLower().Contains("detail"))
                {
                    mats[i] = mat2;
                }
                else
                {
                    mats[i] = mat1;
                }
            }
            mr.sharedMaterials = mats;
        }

        // Save prefab
        string prefabPath = resFolder + "/HospitalPrefab.prefab";
        PrefabUtility.SaveAsPrefabAsset(rootWrapper, prefabPath);
        Debug.Log("[HospitalAssetProcessor] Created clean hospital prefab at: " + prefabPath);

        // Cleanup temp objects
        Object.DestroyImmediate(instance);
        Object.DestroyImmediate(rootWrapper);

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();

        // Write inspection JSON
        string outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../AI-Predictive-Traffic/scratch"));
        if (!Directory.Exists(outDir)) Directory.CreateDirectory(outDir);
        string jsonPath = Path.Combine(outDir, "hospital_model_inspection.json");
        string json = JsonUtility.ToJson(inspection, true);
        File.WriteAllText(jsonPath, json);
        Debug.Log("[HospitalAssetProcessor] Wrote inspection report to: " + jsonPath);
    }

    private static void ConfigureTexture(string path)
    {
        TextureImporter ti = AssetImporter.GetAtPath(path) as TextureImporter;
        if (ti != null)
        {
            ti.textureType = TextureImporterType.Default;
            ti.isReadable = true;
            ti.mipmapEnabled = true;
            ti.filterMode = FilterMode.Bilinear;
            ti.wrapMode = TextureWrapMode.Repeat;
            ti.SaveAndReimport();
        }
    }
}
