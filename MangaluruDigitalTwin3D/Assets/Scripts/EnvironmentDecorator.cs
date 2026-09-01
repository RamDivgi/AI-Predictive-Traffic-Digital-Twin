using UnityEngine;

public class EnvironmentDecorator : MonoBehaviour
{
    public int treeCount = 100;
    public float mapSizeX = 1000f;
    public float mapSizeZ = 1000f;

    void Start()
    {
        return; // Disabled for presentation performance
        // Load tree prefabs
        GameObject[] treePrefabs = new GameObject[]
        {
            Resources.Load<GameObject>("Trees/Fir"),
            Resources.Load<GameObject>("Trees/Maple"),
            Resources.Load<GameObject>("Trees/Pine")
        };

        if (treePrefabs[0] == null) return;

        GameObject treesParent = new GameObject("Trees");
        treesParent.transform.parent = this.transform;

        // Deterministic random to prevent trees changing every run
        Random.InitState(42);

        for (int i = 0; i < treeCount; i++)
        {
            float x = Random.Range(-mapSizeX / 2, mapSizeX / 2);
            float z = Random.Range(-mapSizeZ / 2, mapSizeZ / 2);

            // Simple heuristic to avoid the direct center where the main roads are
            if (Mathf.Abs(x) < 100f && Mathf.Abs(z) < 100f) continue;

            GameObject prefab = treePrefabs[Random.Range(0, treePrefabs.Length)];
            if (prefab != null)
            {
                GameObject tree = Instantiate(prefab, new Vector3(x, 0, z), Quaternion.Euler(0, Random.Range(0, 360), 0));
                tree.transform.parent = treesParent.transform;
                
                // Add some scale variation
                float scale = Random.Range(0.8f, 1.5f);
                tree.transform.localScale = new Vector3(scale, scale, scale);
                
                // Remove colliders for performance
                Collider col = tree.GetComponent<Collider>();
                if (col != null) Destroy(col);
            }
        }
    }
}
