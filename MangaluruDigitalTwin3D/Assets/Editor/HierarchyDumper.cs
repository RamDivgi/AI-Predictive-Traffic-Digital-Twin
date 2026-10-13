using UnityEngine;
using UnityEditor;
using System.IO;

public class HierarchyDumper
{
    [MenuItem("Tools/Dump Traffic Signal Hierarchy")]
    public static void DumpHierarchy()
    {
        // Try to find the root object. Since the name is truncated, we'll look for an object that has a child named "green_light"
        GameObject root = null;
        foreach (GameObject obj in Object.FindObjectsOfType<GameObject>())
        {
            if (obj.transform.Find("green_light") != null && obj.transform.Find("red_light") != null)
            {
                root = obj;
                break;
            }
        }

        if (root == null)
        {
            Debug.LogError("Could not find an object with green_light and red_light children.");
            return;
        }

        string report = "=== HIERARCHY DUMP ===\n";
        DumpNode(root.transform, "", ref report);

        string path = "d:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/unity_hierarchy_dump.txt";
        File.WriteAllText(path, report);
        Debug.Log("Hierarchy dumped to " + path);
    }

    private static void DumpNode(Transform t, string indent, ref string report)
    {
        report += $"{indent}{t.name} (Pos: {t.localPosition}, Rot: {t.localRotation.eulerAngles}, Scale: {t.localScale})\n";
        
        MeshFilter mf = t.GetComponent<MeshFilter>();
        if (mf != null && mf.sharedMesh != null)
        {
            report += $"{indent}  - Mesh: {mf.sharedMesh.name}\n";
        }
        
        Renderer r = t.GetComponent<Renderer>();
        if (r != null)
        {
            report += $"{indent}  - Renderer: {r.GetType().Name}\n";
            foreach (Material m in r.sharedMaterials)
            {
                if (m != null) report += $"{indent}  - Material: {m.name}\n";
            }
        }
        
        for (int i = 0; i < t.childCount; i++)
        {
            DumpNode(t.GetChild(i), indent + "  ", ref report);
        }
    }
}
