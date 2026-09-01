using UnityEngine;

public class VehicleSmoother : MonoBehaviour
{
    private Vector3 previousPosition;
    private Quaternion previousRotation;
    private Vector3 targetPosition;
    private Quaternion targetRotation;
    
    private float timeSinceLastUpdate = 0f;
    private const float SUMO_STEP_LENGTH = 0.1f;
    private bool isInitialized = false;

    public void UpdateTarget(Vector3 pos, Quaternion rot)
    {
        if (!isInitialized)
        {
            transform.localPosition = pos;
            transform.localRotation = rot;
            previousPosition = pos;
            previousRotation = rot;
            targetPosition = pos;
            targetRotation = rot;
            isInitialized = true;
        }
        else
        {
            // Use current transform position as start of interpolation
            previousPosition = transform.localPosition;
            previousRotation = transform.localRotation;
            
            targetPosition = pos;
            targetRotation = rot;
        }
        
        timeSinceLastUpdate = 0f;
    }

    public void ResetState()
    {
        isInitialized = false;
    }

    void Update()
    {
        if (!isInitialized) return;

        timeSinceLastUpdate += Time.deltaTime;
        float t = Mathf.Clamp01(timeSinceLastUpdate / SUMO_STEP_LENGTH);

        transform.localPosition = Vector3.Lerp(previousPosition, targetPosition, t);
        transform.localRotation = Quaternion.Lerp(previousRotation, targetRotation, t);
    }
}
