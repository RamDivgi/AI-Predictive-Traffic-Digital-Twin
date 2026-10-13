using UnityEngine;

public enum CameraState
{
    Overview,
    Transitioning,
    Following
}

public class AmbulanceCameraFollow : MonoBehaviour
{
    public Transform target;
    
    [Header("Camera Settings")]
    public float followDistance = 25f;
    public float height = 15f;
    public float lookAhead = 15f;
    
    [Header("Smoothness")]
    public float transitionDuration = 3f;
    public float positionSmoothTime = 0.5f;
    public float rotationSmoothTime = 0.3f;
    
    [Header("State")]
    public CameraState currentState = CameraState.Overview;
    
    // Centered on the current exported Mangaluru network bounds.
    private Vector3 overviewPosition = new Vector3(1612f, 430f, 1150f);
    private Vector3 overviewTarget = new Vector3(1612f, 0f, 1673f);
    private Quaternion overviewRotation;
    
    private Vector3 velocity = Vector3.zero;
    private float transitionTimer = 0f;
    
    private Vector3 lastTargetPosition;

    void Start()
    {
        overviewRotation = Quaternion.LookRotation(overviewTarget - overviewPosition);
        transform.position = overviewPosition;
        transform.rotation = overviewRotation;
        GetComponent<Camera>().farClipPlane = 5000f;
        
        FindTarget();
        Debug.Log("AmbulanceCameraFollow: Started in Overview state.");
    }
    
    void FindTarget()
    {
        if (target == null)
        {
            GameObject amb = GameObject.Find("Ambulance");
            if (amb != null) target = amb.transform;
            else
            {
                AmbulanceReceiver receiver = FindObjectOfType<AmbulanceReceiver>();
                if (receiver != null) target = receiver.transform;
            }
        }
    }

    void LateUpdate()
    {
        if (target == null) FindTarget();

        bool targetIsActive = (target != null && target.position.sqrMagnitude > 100f);

        switch (currentState)
        {
            case CameraState.Overview:
                if (targetIsActive)
                {
                    currentState = CameraState.Transitioning;
                    transitionTimer = 0f;
                    Debug.Log("AmbulanceCameraFollow: Transitioning to ambulance.");
                }
                break;
                
            case CameraState.Transitioning:
                transitionTimer += Time.deltaTime;
                float t = Mathf.Clamp01(transitionTimer / transitionDuration);
                
                // Use a smooth ease-in-out curve
                float smoothT = t * t * (3f - 2f * t);
                
                Vector3 targetDesiredPos = GetDesiredPosition();
                Quaternion targetDesiredRot = GetDesiredRotation();
                
                transform.position = Vector3.Lerp(overviewPosition, targetDesiredPos, smoothT);
                transform.rotation = Quaternion.Slerp(overviewRotation, targetDesiredRot, smoothT);
                
                if (t >= 1f)
                {
                    currentState = CameraState.Following;
                    Debug.Log("AmbulanceCameraFollow: Following ambulance.");
                }
                break;
                
            case CameraState.Following:
                if (!targetIsActive)
                {
                    currentState = CameraState.Overview;
                    Debug.Log("AmbulanceCameraFollow: Returning to Overview.");
                    break;
                }
                
                UpdateFollow();
                break;
        }
    }
    
    private Vector3 GetDesiredPosition()
    {
        Vector3 targetForward = target.forward;
        if (targetForward == Vector3.zero) targetForward = Vector3.forward;
        
        return target.position - (targetForward * followDistance) + (Vector3.up * height);
    }
    
    private Quaternion GetDesiredRotation()
    {
        Vector3 targetForward = target.forward;
        if (targetForward == Vector3.zero) targetForward = Vector3.forward;
        
        Vector3 lookAtPoint = target.position + (targetForward * lookAhead);
        Vector3 direction = (lookAtPoint - transform.position).normalized;
        if (direction != Vector3.zero)
        {
            return Quaternion.LookRotation(direction);
        }
        return transform.rotation;
    }
    
    private void UpdateFollow()
    {
        Vector3 desiredPosition = GetDesiredPosition();
        Quaternion desiredRotation = GetDesiredRotation();
        
        transform.position = Vector3.SmoothDamp(transform.position, desiredPosition, ref velocity, positionSmoothTime);
        
        // Slerp rotation for buttery smooth look-ahead tracking
        transform.rotation = Quaternion.Slerp(transform.rotation, desiredRotation, Time.deltaTime * (1f / rotationSmoothTime));
        
        lastTargetPosition = target.position;
    }
}
