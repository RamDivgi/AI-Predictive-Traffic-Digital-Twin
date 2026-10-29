using UnityEngine;

/// <summary>
/// Keeps hospital name labels upright and facing the active camera horizontally (yaw only),
/// ensuring crisp, distortion-free readability from gameplay, follow-cam, and aerial views.
/// </summary>
public class HospitalBillboard : MonoBehaviour
{
    void LateUpdate()
    {
        Camera cam = GetActiveCamera();
        if (cam != null)
        {
            AlignToCamera(cam);
        }
    }

    /// <summary>
    /// Explicitly aligns the billboard to face the specified camera horizontally.
    /// Can be called immediately before camera rendering to guarantee 100% alignment.
    /// </summary>
    public void AlignToCamera(Camera cam)
    {
        if (cam == null) return;

        // Vector from camera to billboard on horizontal XZ plane
        Vector3 camToTarget = transform.position - cam.transform.position;
        camToTarget.y = 0f;

        if (camToTarget.sqrMagnitude > 0.01f)
        {
            // Point billboard local +Z away from camera so local -Z faces directly toward camera
            transform.rotation = Quaternion.LookRotation(camToTarget.normalized, Vector3.up);
        }
    }

    private Camera GetActiveCamera()
    {
        // 1. Check for active capture camera (e.g. during visual acceptance automation)
        GameObject capObj = GameObject.Find("VisualAcceptanceCamera");
        if (capObj != null)
        {
            Camera capCam = capObj.GetComponent<Camera>();
            if (capCam != null && capCam.isActiveAndEnabled) return capCam;
        }

        // 2. Check current rendering camera
        if (Camera.current != null && Camera.current.isActiveAndEnabled)
        {
            return Camera.current;
        }

        // 3. Check main camera
        if (Camera.main != null && Camera.main.isActiveAndEnabled)
        {
            return Camera.main;
        }

        // 4. Fallback to any active camera
        Camera[] allCams = Camera.allCameras;
        if (allCams != null)
        {
            for (int i = 0; i < allCams.Length; i++)
            {
                if (allCams[i] != null && allCams[i].isActiveAndEnabled)
                {
                    return allCams[i];
                }
            }
        }

        return null;
    }
}
