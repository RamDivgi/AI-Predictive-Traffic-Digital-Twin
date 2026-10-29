using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

public static class PrefabBoundsDumper
{
    [System.Serializable]
    public class PrefabBoundInfo
    {
        public string name;
        public float centerX;
        public float centerY;
        public float centerZ;
        public float sizeX;
        public float sizeY;
        public float sizeZ;
        public float minX;
        public float maxX;
        public float minZ;
        public float maxZ;
    }

    [System.Serializable]
    public class DumpPayload
    {
        public List<PrefabBoundInfo> prefabs = new List<PrefabBoundInfo>();
    }

    [MenuItem("Tools/Dump Prefab Bounds")]
    public static void DumpBounds()
    {
        string[] prefabPaths = new string[]
        {
            "Buildings/Bldg_House01",
            "Buildings/Bldg_House02",
            "Buildings/Bldg_House05",
            "Buildings/Bldg_House07",
            "Buildings/Bldg_House11",
            "Buildings/Bldg_Commercial01",
            "Buildings/Bldg_Commercial02",
            "Buildings/Bldg_Commercial03",
            "Buildings/Bldg_Office01",
            "Buildings/Bldg_Office02"
        };

        DumpPayload payload = new DumpPayload();

        foreach (string path in prefabPaths)
        {
            GameObject prefab = Resources.Load<GameObject>(path);
            if (prefab == null)
            {
                Debug.LogError("Could not load prefab: " + path);
                continue;
            }

            GameObject instance = Object.Instantiate(prefab);
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.identity;
            instance.transform.localScale = Vector3.one;

            Bounds combined = new Bounds();
            bool hasBounds = false;

            Renderer[] renderers = instance.GetComponentsInChildren<Renderer>();
            foreach (Renderer r in renderers)
            {
                if (!hasBounds)
                {
                    combined = r.bounds;
                    hasBounds = true;
                }
                else
                {
                    combined.Encapsulate(r.bounds);
                }
            }

            MeshFilter[] meshFilters = instance.GetComponentsInChildren<MeshFilter>();
            foreach (MeshFilter mf in meshFilters)
            {
                if (mf.sharedMesh != null)
                {
                    // Transform mesh bounds to instance local space
                    Matrix4x4 localToInstance = instance.transform.worldToLocalMatrix * mf.transform.localToWorldMatrix;
                    Bounds b = mf.sharedMesh.bounds;
                    Vector3[] corners = new Vector3[8]
                    {
                        localToInstance.MultiplyPoint3x4(new Vector3(b.min.x, b.min.y, b.min.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.min.x, b.min.y, b.max.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.min.x, b.max.y, b.min.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.min.x, b.max.y, b.max.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.max.x, b.min.y, b.min.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.max.x, b.min.y, b.max.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.max.x, b.max.y, b.min.z)),
                        localToInstance.MultiplyPoint3x4(new Vector3(b.max.x, b.max.y, b.max.z))
                    };

                    foreach (var c in corners)
                    {
                        if (!hasBounds)
                        {
                            combined = new Bounds(c, Vector3.zero);
                            hasBounds = true;
                        }
                        else
                        {
                            combined.Encapsulate(c);
                        }
                    }
                }
            }

            PrefabBoundInfo info = new PrefabBoundInfo
            {
                name = Path.GetFileName(path),
                centerX = combined.center.x,
                centerY = combined.center.y,
                centerZ = combined.center.z,
                sizeX = combined.size.x,
                sizeY = combined.size.y,
                sizeZ = combined.size.z,
                minX = combined.min.x,
                maxX = combined.max.x,
                minZ = combined.min.z,
                maxZ = combined.max.z
            };
            payload.prefabs.Add(info);

            Object.DestroyImmediate(instance);
        }

        string outputPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../AI-Predictive-Traffic/scratch/prefab_bounds.json"));
        File.WriteAllText(outputPath, JsonUtility.ToJson(payload, true));
        Debug.Log("[PrefabBoundsDumper] Successfully exported prefab bounds to: " + outputPath);
    }
}
