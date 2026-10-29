using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;

[System.Serializable]
public class TelemetryPayload
{
    public string hospital;
    public float overall_eta;
    public string next_junction;
    public float next_eta;
    public string traffic_condition;
    public int queue_length;
    public string emergency_control;
    public string signal_color;
    public string route_type;
}

public class DashboardController : MonoBehaviour
{
    [Header("UI Configuration")]
    [Tooltip("Enable or disable the 2D semi-transparent dashboard overlay on the left side of the Game view.")]
    public bool showDashboardOverlay = false;

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;
    private int listenPort = 5010;

    private object dataLock = new object();
    private TelemetryPayload latestPayload = null;
    private bool hasNewData = false;
    private DateTime lastPacketUtc = DateTime.MinValue;

    // UI Elements
    private GameObject canvasObj;
    private Text ambulanceStatusText;
    private Text destinationText;
    private Text currentEtaText;
    private Text nextJunctionText;
    private Text nextJunctionEtaText;
    private Text trafficConditionText;
    private Text queueLengthText;
    private Text emergencyControlText;
    private Text signalColorText;
    private Text routeTypeText;
    private Text reasonText;

    void Start()
    {
        if (showDashboardOverlay)
        {
            CreateUI();
            StartUDPReceiver();
        }
        else
        {
            CleanupUI();
            Debug.Log("DashboardController: 2D dashboard overlay disabled for unobstructed 3D simulation view.");
        }
    }

    private void CleanupUI()
    {
        GameObject canvas = GameObject.Find("AI_DashboardCanvas");
        if (canvas != null)
        {
            Destroy(canvas);
        }
    }

    void OnValidate()
    {
        if (Application.isPlaying && canvasObj != null)
        {
            canvasObj.SetActive(showDashboardOverlay);
        }
    }

    private void CreateUI()
    {
        if (!showDashboardOverlay) return;

        // Auto-generate UI Canvas if not present
        canvasObj = new GameObject("AI_DashboardCanvas");
        Canvas canvas = canvasObj.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        canvasObj.AddComponent<CanvasScaler>().uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        canvasObj.AddComponent<GraphicRaycaster>();
        
        EventSystem es = FindAnyObjectByType<EventSystem>();
        if (es == null)
        {
            GameObject esObj = new GameObject("EventSystem");
            es = esObj.AddComponent<EventSystem>();
        }

        // Remove legacy StandaloneInputModule if present to prevent InvalidOperationException
        StandaloneInputModule legacyModule = es.GetComponent<StandaloneInputModule>();
        if (legacyModule != null)
        {
            Destroy(legacyModule);
        }

        // Add modern InputSystemUIInputModule if not present and assign default actions
        InputSystemUIInputModule inputModule = es.GetComponent<InputSystemUIInputModule>();
        if (inputModule == null)
        {
            inputModule = es.gameObject.AddComponent<InputSystemUIInputModule>();
            inputModule.AssignDefaultActions();
        }

        // Background Panel
        GameObject panelObj = new GameObject("DashboardPanel");
        panelObj.transform.SetParent(canvasObj.transform, false);
        Image bgImage = panelObj.AddComponent<Image>();
        bgImage.color = new Color(0.1f, 0.1f, 0.15f, 0.9f); // Dark translucent
        RectTransform panelRect = panelObj.GetComponent<RectTransform>();
        panelRect.anchorMin = new Vector2(0, 0);
        panelRect.anchorMax = new Vector2(0, 1);
        panelRect.pivot = new Vector2(0, 0.5f);
        panelRect.sizeDelta = new Vector2(350, 0); // 350px width, stretch height

        // Title
        CreateText(panelObj.transform, "AI EMERGENCY TRAFFIC CONTROL", new Vector2(10, -20), 18, FontStyle.Bold, Color.cyan);

        // Telemetry Fields
        int yOffset = -60;
        int ySpacing = 30;

        ambulanceStatusText = CreateText(panelObj.transform, "Ambulance: WAITING", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        destinationText = CreateText(panelObj.transform, "Destination: None", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        currentEtaText = CreateText(panelObj.transform, "Current ETA: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        routeTypeText = CreateText(panelObj.transform, "Route: NORMAL", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing * 2;

        CreateText(panelObj.transform, "--- UPCOMING JUNCTION ---", new Vector2(10, yOffset), 14, FontStyle.Bold, Color.yellow);
        yOffset -= ySpacing;
        nextJunctionText = CreateText(panelObj.transform, "Next Junction: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        nextJunctionEtaText = CreateText(panelObj.transform, "Junction ETA: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        trafficConditionText = CreateText(panelObj.transform, "Traffic Condition: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        queueLengthText = CreateText(panelObj.transform, "Queue: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing * 2;

        CreateText(panelObj.transform, "--- AI DECISION ---", new Vector2(10, yOffset), 14, FontStyle.Bold, Color.magenta);
        yOffset -= ySpacing;
        emergencyControlText = CreateText(panelObj.transform, "Emergency Control: NORMAL", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);
        yOffset -= ySpacing;
        reasonText = CreateText(panelObj.transform, "Reason: --", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.cyan);
        yOffset -= ySpacing;
        signalColorText = CreateText(panelObj.transform, "Signal: UNKNOWN", new Vector2(10, yOffset), 14, FontStyle.Normal, Color.white);

        // Buttons for hospital selection
        yOffset -= ySpacing * 2;
        CreateText(panelObj.transform, "--- DESTINATION OVERRIDE ---", new Vector2(10, yOffset), 14, FontStyle.Bold, Color.cyan);
        yOffset -= ySpacing;

        CreateButton(panelObj.transform, "Highland Hospital", "highland_hospital", new Vector2(10, yOffset));
        yOffset -= ySpacing + 10;
        CreateButton(panelObj.transform, "KMC Hospital", "kmc_hospital", new Vector2(10, yOffset));
    }

    private Font cachedFont = null;

    private Font GetDefaultFont()
    {
        if (cachedFont != null) return cachedFont;

        // In Unity 6 (6000.x), LegacyRuntime.ttf replaces the deprecated Arial.ttf
        try
        {
            cachedFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }
        catch (Exception) {}

        if (cachedFont == null)
        {
            try
            {
                cachedFont = Resources.GetBuiltinResource<Font>("Arial.ttf");
            }
            catch (Exception) {}
        }

        if (cachedFont == null)
        {
            try
            {
                cachedFont = Font.CreateDynamicFontFromOSFont("Arial", 14);
            }
            catch (Exception) {}
        }

        return cachedFont;
    }

    private Text CreateText(Transform parent, string textStr, Vector2 pos, int fontSize, FontStyle style, Color color)
    {
        GameObject textObj = new GameObject("Text");
        textObj.transform.SetParent(parent, false);
        Text t = textObj.AddComponent<Text>();
        t.font = GetDefaultFont();
        t.text = textStr;
        t.fontSize = fontSize;
        t.fontStyle = style;
        t.color = color;
        t.alignment = TextAnchor.UpperLeft;

        RectTransform rect = textObj.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0, 1);
        rect.anchorMax = new Vector2(0, 1);
        rect.pivot = new Vector2(0, 1);
        rect.anchoredPosition = pos;
        rect.sizeDelta = new Vector2(330, 30);
        return t;
    }

    private void CreateButton(Transform parent, string label, string hospitalId, Vector2 pos)
    {
        GameObject btnObj = new GameObject("Button_" + hospitalId);
        btnObj.transform.SetParent(parent, false);
        Image bg = btnObj.AddComponent<Image>();
        bg.color = new Color(0.2f, 0.4f, 0.8f, 1f);
        Button btn = btnObj.AddComponent<Button>();

        RectTransform rect = btnObj.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0, 1);
        rect.anchorMax = new Vector2(0, 1);
        rect.pivot = new Vector2(0, 1);
        rect.anchoredPosition = pos;
        rect.sizeDelta = new Vector2(200, 30);

        GameObject textObj = new GameObject("Text");
        textObj.transform.SetParent(btnObj.transform, false);
        Text t = textObj.AddComponent<Text>();
        t.font = GetDefaultFont();
        t.text = label;
        t.fontSize = 14;
        t.color = Color.white;
        t.alignment = TextAnchor.MiddleCenter;
        
        RectTransform txtRect = textObj.GetComponent<RectTransform>();
        txtRect.anchorMin = new Vector2(0, 0);
        txtRect.anchorMax = new Vector2(1, 1);
        txtRect.sizeDelta = Vector2.zero;

        btn.onClick.AddListener(() => SendHospitalSelection(hospitalId));
    }

    private void SendHospitalSelection(string hospitalId)
    {
        try
        {
            UdpClient sender = new UdpClient();
            string jsonMsg = $"{{\"type\": \"set_hospital\", \"hospital_id\": \"{hospitalId}\"}}";
            byte[] bytes = Encoding.UTF8.GetBytes(jsonMsg);
            sender.Send(bytes, bytes.Length, "127.0.0.1", 5009);
            Debug.Log("Sent hospital selection: " + hospitalId);
            sender.Close();
        }
        catch (Exception e)
        {
            Debug.LogError("Error sending hospital selection: " + e.Message);
        }
    }

    private void StartUDPReceiver()
    {
        if (!showDashboardOverlay) return;

        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("DashboardController: Listening on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);
            while (isRunning)
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);
                try
                {
                    TelemetryPayload payload = JsonUtility.FromJson<TelemetryPayload>(text);
                    if (payload != null)
                    {
                        lock (dataLock)
                        {
                            latestPayload = payload;
                            hasNewData = true;
                            lastPacketUtc = DateTime.UtcNow;
                        }
                    }
                }
                catch (Exception) {}
            }
        }
        catch (Exception e)
        {
            if (isRunning) Debug.LogError("UDP Receive Thread Error: " + e.Message);
        }
    }

    void Update()
    {
        if (!showDashboardOverlay) return;

        TelemetryPayload payloadToDraw = null;
        DateTime packetTime = DateTime.MinValue;
        lock (dataLock)
        {
            if (hasNewData)
            {
                payloadToDraw = latestPayload;
                hasNewData = false;
            }
            packetTime = lastPacketUtc;
        }

        if (packetTime != DateTime.MinValue && (DateTime.UtcNow - packetTime).TotalSeconds > 5.0)
        {
            if (ambulanceStatusText != null)
            {
                ambulanceStatusText.text = "Ambulance: TELEMETRY PAUSED / STALE";
                ambulanceStatusText.color = Color.yellow;
            }
        }

        if (payloadToDraw != null)
        {
            ambulanceStatusText.text = "Ambulance: EN ROUTE";
            ambulanceStatusText.color = Color.green;
            destinationText.text = "Destination: " + payloadToDraw.hospital;
            currentEtaText.text = "Current ETA: " + payloadToDraw.overall_eta.ToString("F1") + " s";
            routeTypeText.text = "Route: " + payloadToDraw.route_type;
            
            string junc = payloadToDraw.next_junction;
            if (junc.Length > 15) junc = junc.Substring(0, 15) + "...";
            nextJunctionText.text = "Next Junction: " + junc;
            
            nextJunctionEtaText.text = "Junction ETA: " + payloadToDraw.next_eta.ToString("F1") + " s";
            trafficConditionText.text = "Traffic Condition: " + payloadToDraw.traffic_condition;
            
            if (payloadToDraw.traffic_condition == "HIGH") trafficConditionText.color = Color.red;
            else if (payloadToDraw.traffic_condition == "MODERATE") trafficConditionText.color = Color.yellow;
            else trafficConditionText.color = Color.green;

            queueLengthText.text = "Queue: " + payloadToDraw.queue_length + " vehicles";
            emergencyControlText.text = "Emergency Control: " + payloadToDraw.emergency_control;
            
            if (payloadToDraw.emergency_control == "PREEMPTING") {
                emergencyControlText.color = Color.red;
                reasonText.text = "REASON: HIGH QUEUE + AMBULANCE APPROACH";
            }
            else if (payloadToDraw.emergency_control == "PREPARING") {
                emergencyControlText.color = Color.yellow;
                reasonText.text = "REASON: PREPARING CORRIDOR";
            }
            else {
                emergencyControlText.color = Color.white;
                reasonText.text = "REASON: NORMAL CONDITIONS";
            }

            signalColorText.text = "Signal: " + payloadToDraw.signal_color;
            if (payloadToDraw.signal_color == "GREEN") signalColorText.color = Color.green;
            else if (payloadToDraw.signal_color == "RED") signalColorText.color = Color.red;
            else if (payloadToDraw.signal_color == "YELLOW") signalColorText.color = Color.yellow;
            else signalColorText.color = Color.white;
        }
    }

    void OnDestroy()
    {
        isRunning = false;
        if (udpClient != null)
        {
            try { udpClient.Close(); } catch (Exception) {}
        }
        if (receiveThread != null && receiveThread.IsAlive)
        {
            try { receiveThread.Join(200); } catch (Exception) {}
        }
    }
}
