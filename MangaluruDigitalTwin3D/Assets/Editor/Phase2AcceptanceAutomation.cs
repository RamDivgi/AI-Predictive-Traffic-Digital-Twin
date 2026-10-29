using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class Phase2AcceptanceAutomation
{
    private static bool isCommandLineRun = false;
    private static bool isAutomationActive = false;
    private static bool pendingPlayModeStart = false;

    static Phase2AcceptanceAutomation()
    {
        EditorApplication.update += MonitorTrigger;
        EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
    }

    private static void OnPlayModeStateChanged(PlayModeStateChange state)
    {
        if (state == PlayModeStateChange.EnteredEditMode)
        {
            isAutomationActive = false;
            VisualAcceptanceAgent.IsAutomationActive = false;
        }
    }

    public static void RunAcceptanceSuite()
    {
        RunFromCommandLine();
    }

    public static void RunFromCommandLine()
    {
        isCommandLineRun = true;
        isAutomationActive = true;
        RunVisualAcceptance();
    }

    [MenuItem("Mangaluru/Run Phase 2 Visual Acceptance")]
    public static void RunVisualAcceptance()
    {
        Debug.Log("[Phase2AcceptanceAutomation] Triggering Phase 2 Visual Acceptance Suite...");
        isAutomationActive = true;
        VisualAcceptanceAgent.IsAutomationActive = true;
        VisualAcceptanceAgent.HasRun = false;

        string flagPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../docs/screenshots/acceptance_complete.flag"));
        if (File.Exists(flagPath))
        {
            try { File.Delete(flagPath); } catch {}
        }

        if (EditorApplication.isPlaying)
        {
            pendingPlayModeStart = true;
            EditorApplication.isPlaying = false;
            return;
        }

        if (!EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorSceneManager.OpenScene("Assets/Scenes/SampleScene.unity");
            EditorApplication.isPlaying = true;
        }
    }

    private static void MonitorTrigger()
    {
        if (pendingPlayModeStart && !EditorApplication.isPlaying && !EditorApplication.isPlayingOrWillChangePlaymode)
        {
            pendingPlayModeStart = false;
            isAutomationActive = true;
            VisualAcceptanceAgent.IsAutomationActive = true;
            VisualAcceptanceAgent.HasRun = false;
            EditorSceneManager.OpenScene("Assets/Scenes/SampleScene.unity");
            EditorApplication.isPlaying = true;
            return;
        }

        string triggerPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../run_acceptance.trigger"));
        if (File.Exists(triggerPath))
        {
            try { File.Delete(triggerPath); } catch {}
            RunVisualAcceptance();
        }

        // Only monitor and exit Play Mode if this session was explicitly launched as an automated test run
        if (isAutomationActive || Application.isBatchMode || isCommandLineRun)
        {
            string flagPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../docs/screenshots/acceptance_complete.flag"));
            if (File.Exists(flagPath) && EditorApplication.isPlaying)
            {
                Debug.Log("[Phase2AcceptanceAutomation] Acceptance test completed in Play Mode! Stopping Play Mode...");
                isAutomationActive = false;
                VisualAcceptanceAgent.IsAutomationActive = false;
                try { File.Delete(flagPath); } catch {}
                EditorApplication.isPlaying = false;
                if (Application.isBatchMode || isCommandLineRun)
                {
                    Debug.Log("[Phase2AcceptanceAutomation] Exiting Editor process...");
                    EditorApplication.Exit(0);
                }
            }
        }
    }
}
