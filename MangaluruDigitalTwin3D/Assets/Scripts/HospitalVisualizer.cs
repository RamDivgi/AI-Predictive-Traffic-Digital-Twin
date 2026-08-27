using UnityEngine;

public class HospitalVisualizer : MonoBehaviour
{
    // Exact destination coordinate from SUMO hospitals.add.xml
    public float sumoX = 1687.469f;
    public float sumoY = 1134.98f;
    
    void Start()
    {
        CreateHospitalModel();
    }
    
    void CreateHospitalModel()
    {
        // 1. Convert to Unity coordinates
        // Unity.X = SUMO.X
        // Unity.Y = 0 (ground)
        // Unity.Z = SUMO.Y
        Vector3 position = new Vector3(sumoX, 0f, sumoY);
        
        // 2. Create the main hospital building (large compound object)
        GameObject hospital = new GameObject("HighlandHospital");
        hospital.transform.position = position;
        hospital.transform.parent = this.transform;
        
        // Main block
        GameObject mainBlock = GameObject.CreatePrimitive(PrimitiveType.Cube);
        mainBlock.transform.parent = hospital.transform;
        mainBlock.transform.localPosition = new Vector3(0, 10f, 0); // 20m tall
        mainBlock.transform.localScale = new Vector3(40f, 20f, 30f);
        Destroy(mainBlock.GetComponent<Collider>()); // optimize
        
        Material whiteMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        whiteMat.color = new Color(0.9f, 0.9f, 0.95f);
        mainBlock.GetComponent<Renderer>().material = whiteMat;
        
        // Red Cross on top
        Material redMat = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        redMat.color = Color.red;
        
        CreateCross(hospital.transform, new Vector3(0, 23f, 0), Vector3.up, redMat, 8f); // Roof cross
        CreateCross(hospital.transform, new Vector3(0, 15f, -15.1f), Vector3.back, redMat, 6f); // Front cross
        
        // Hospital Sign (3D text)
        GameObject signObj = new GameObject("HospitalSign");
        signObj.transform.parent = hospital.transform;
        signObj.transform.localPosition = new Vector3(0, 26f, 0);
        
        TextMesh tm = signObj.AddComponent<TextMesh>();
        tm.text = "HIGHLAND HOSPITAL";
        tm.characterSize = 2f;
        tm.fontSize = 48;
        tm.anchor = TextAnchor.MiddleCenter;
        tm.alignment = TextAlignment.Center;
        tm.color = Color.red;
        
        Debug.Log($"Highland Hospital created at Unity({position.x}, {position.y}, {position.z})");
    }
    
    private void CreateCross(Transform parent, Vector3 localPosition, Vector3 forward, Material mat, float scale)
    {
        GameObject vBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        vBar.transform.parent = parent;
        vBar.transform.localPosition = localPosition;
        vBar.transform.localRotation = Quaternion.LookRotation(forward);
        vBar.transform.localScale = new Vector3(scale * 0.3f, scale, scale * 0.1f);
        Destroy(vBar.GetComponent<Collider>());
        vBar.GetComponent<Renderer>().material = mat;
        
        GameObject hBar = GameObject.CreatePrimitive(PrimitiveType.Cube);
        hBar.transform.parent = parent;
        hBar.transform.localPosition = localPosition;
        hBar.transform.localRotation = Quaternion.LookRotation(forward);
        hBar.transform.localScale = new Vector3(scale, scale * 0.3f, scale * 0.1f);
        Destroy(hBar.GetComponent<Collider>());
        hBar.GetComponent<Renderer>().material = mat;
    }
}
