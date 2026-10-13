using UnityEngine;

public class VehicleSmoother : MonoBehaviour
{
    private Vector3 previousPosition;
    private Quaternion previousRotation;
    private Vector3 targetPosition;
    private Quaternion targetRotation;

    private float timeSinceLastUpdate = 0f;
    private bool isInitialized = false;
    private bool isStationary = false;

    // Timing constants & configuration
    private const float DEFAULT_STEP_LENGTH = 0.1f;
    private const float MIN_VALID_INTERVAL = 0.03f;
    private const float MAX_VALID_INTERVAL = 0.5f;
    private const float INTERVAL_SMOOTHING_FACTOR = 0.25f;
    private const float MIN_ESTIMATED_INTERVAL = 0.05f;
    private const float MAX_ESTIMATED_INTERVAL = 0.25f;

    // Safety thresholds
    private const float MAX_TELEPORT_DISTANCE = 20.0f;
    private const float MAX_GAP_DURATION = 1.5f;
    private const float STATIONARY_EPSILON_SQ = 0.0001f; // (0.01m)^2

    // Damped extrapolation parameters for delayed packet grace period
    private const float MAX_EXTRAPOLATION_RATIO = 0.10f;
    private const float DAMPING_TAU = 0.08f;

    private float estimatedStepDuration = DEFAULT_STEP_LENGTH;

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
            estimatedStepDuration = DEFAULT_STEP_LENGTH;
            timeSinceLastUpdate = 0f;
            isStationary = false;
            isInitialized = true;
            return;
        }

        // Check for long gap or teleport / respawn across map
        float distSq = (pos - transform.localPosition).sqrMagnitude;
        if (distSq > (MAX_TELEPORT_DISTANCE * MAX_TELEPORT_DISTANCE) || timeSinceLastUpdate > MAX_GAP_DURATION)
        {
            transform.localPosition = pos;
            transform.localRotation = rot;
            previousPosition = pos;
            previousRotation = rot;
            targetPosition = pos;
            targetRotation = rot;
            estimatedStepDuration = DEFAULT_STEP_LENGTH;
            timeSinceLastUpdate = 0f;
            isStationary = false;
            return;
        }

        // Measure actual target-update interval and adaptively update estimated duration
        float actualInterval = timeSinceLastUpdate;
        if (actualInterval >= MIN_VALID_INTERVAL && actualInterval <= MAX_VALID_INTERVAL)
        {
            estimatedStepDuration = Mathf.Lerp(estimatedStepDuration, actualInterval, INTERVAL_SMOOTHING_FACTOR);
        }
        estimatedStepDuration = Mathf.Clamp(estimatedStepDuration, MIN_ESTIMATED_INTERVAL, MAX_ESTIMATED_INTERVAL);

        // Check if vehicle is stationary (repeated identical targets, e.g. at red light / queue)
        if ((pos - targetPosition).sqrMagnitude < STATIONARY_EPSILON_SQ)
        {
            isStationary = true;
            transform.localPosition = pos;
            transform.localRotation = rot;
            previousPosition = pos;
            previousRotation = rot;
            targetPosition = pos;
            targetRotation = rot;
            timeSinceLastUpdate = 0f;
            return;
        }

        // Vehicle is moving: set current transform as new interpolation origin
        isStationary = false;
        previousPosition = transform.localPosition;
        previousRotation = transform.localRotation;
        targetPosition = pos;
        targetRotation = rot;
        timeSinceLastUpdate = 0f;
    }

    public void ResetState()
    {
        isInitialized = false;
        isStationary = false;
        timeSinceLastUpdate = 0f;
        estimatedStepDuration = DEFAULT_STEP_LENGTH;
    }

    void Update()
    {
        if (!isInitialized || isStationary) return;

        timeSinceLastUpdate += Time.deltaTime;
        float normalizedTime = timeSinceLastUpdate / estimatedStepDuration;

        // Position interpolation:
        // Use linear interpolation while within estimated window (normalizedTime <= 1.0f).
        // If the packet is slightly delayed (normalizedTime > 1.0f), provide gentle damped continuation
        // up to at most MAX_EXTRAPOLATION_RATIO so the vehicle does not hit an abrupt zero-velocity stall.
        float posT;
        if (normalizedTime <= 1.0f)
        {
            posT = normalizedTime;
        }
        else
        {
            float overtime = normalizedTime - 1.0f;
            float extra = MAX_EXTRAPOLATION_RATIO * (1.0f - Mathf.Exp(-overtime / DAMPING_TAU));
            posT = 1.0f + extra;
        }

        transform.localPosition = Vector3.LerpUnclamped(previousPosition, targetPosition, posT);

        // Rotation interpolation: strictly clamped to [0, 1] to avoid angular overshooting
        float rotT = Mathf.Clamp01(normalizedTime);
        transform.localRotation = Quaternion.Slerp(previousRotation, targetRotation, rotT);
    }
}
