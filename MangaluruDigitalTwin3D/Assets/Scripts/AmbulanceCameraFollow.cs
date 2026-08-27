using UnityEngine;

public class AmbulanceCameraFollow : MonoBehaviour
{
    public Transform target;
    
    [Header("Camera Settings")]
    public float followDistance = 25f;
    public float height = 15f;
    public float lookAhead = 10f;
    
    [Header("Smoothness")]
    public float positionSmoothness = 5f;
    public float rotationSmoothness = 5f;
    
    private bool isFollowing = true;
    private Vector3 overviewPosition = new Vector3(2000f, 300f, 1500f);
    private Quaternion overviewRotation = Quaternion.Euler(60f, 0f, 0f);
    private float lastLogTime = 0f;

    void Start()
    {
        // Try to find the ambulance if not assigned
        if (target == null)
        {
            GameObject amb = GameObject.Find("Ambulance");
            if (amb != null) target = amb.transform;
            else
            {
                // AmbulanceReceiver might be on a generic GameObject, let's look for the component
                AmbulanceReceiver receiver = FindObjectOfType<AmbulanceReceiver>();
                if (receiver != null) target = receiver.transform;
            }
        }
        
        Debug.Log("AmbulanceCameraFollow started. Target assigned: " + (target != null));
    }

    void Update()
    {
        // Removed old UnityEngine.Input calls to fix Input System compatibility.
        // We will automatically follow the ambulance.
    }

    void LateUpdate()
    {
        // Only follow if the target exists and has moved away from origin (i.e. spawned by SUMO)
        bool hasSpawned = (target != null && target.position.sqrMagnitude > 100f);
        
        if (isFollowing && hasSpawned)
        {
            // Calculate desired position behind and above the target
            Vector3 targetForward = target.forward;
            if (targetForward == Vector3.zero) targetForward = Vector3.forward;
            
            Vector3 desiredPosition = target.position - (targetForward * followDistance) + (Vector3.up * height);
            transform.position = Vector3.Lerp(transform.position, desiredPosition, Time.deltaTime * positionSmoothness);

            // Calculate desired rotation looking ahead of the ambulance
            Vector3 lookAtPoint = target.position + (targetForward * lookAhead);
            Quaternion desiredRotation = Quaternion.LookRotation(lookAtPoint - transform.position);
            transform.rotation = Quaternion.Slerp(transform.rotation, desiredRotation, Time.deltaTime * rotationSmoothness);
        }
        else
        {
            // Move to overview position (Mangaluru city center approx)
            transform.position = Vector3.Lerp(transform.position, overviewPosition, Time.deltaTime * positionSmoothness);
            transform.rotation = Quaternion.Slerp(transform.rotation, overviewRotation, Time.deltaTime * rotationSmoothness);
        }
        
        // Diagnostic Logging
        if (Time.time - lastLogTime > 2.0f)
        {
            if (target != null)
            {
                Debug.Log($"AMBULANCE TARGET:\nGameObject = {target.gameObject.name}\nPosition = {target.position.x:F2}, {target.position.y:F2}, {target.position.z:F2}");
                Debug.Log($"CAMERA TARGET:\nGameObject = {target.gameObject.name}\nPosition = {transform.position.x:F2}, {transform.position.y:F2}, {transform.position.z:F2}");
            }
            lastLogTime = Time.time;
        }
    }
}
