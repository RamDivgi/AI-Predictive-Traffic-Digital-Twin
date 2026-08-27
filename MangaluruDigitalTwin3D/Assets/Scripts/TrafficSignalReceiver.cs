using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

[System.Serializable]
public class SignalData
{
    public string id;
    public string state;
}

[System.Serializable]
public class SignalPayload
{
    public SignalData[] signals;
}

public class TrafficSignalReceiver : MonoBehaviour
{
    public int listenPort = 5007;

    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    private SignalPayload latestPayload;
    private object dataLock = new object();
    
    private int packetsReceived = 0;
    private float lastLogTime = 0f;

    void Start()
    {
        StartUDPReceiver();
    }

    private void StartUDPReceiver()
    {
        isRunning = true;
        receiveThread = new Thread(new ThreadStart(ReceiveData));
        receiveThread.IsBackground = true;
        receiveThread.Start();
        Debug.Log("TrafficSignalReceiver: Started UDP listener on port " + listenPort);
    }

    private void ReceiveData()
    {
        try
        {
            udpClient = new UdpClient(listenPort);
            IPEndPoint anyIP = new IPEndPoint(IPAddress.Any, 0);

            udpClient.Client.ReceiveBufferSize = 65535;

            while (isRunning)
            {
                byte[] data = udpClient.Receive(ref anyIP);
                string text = Encoding.UTF8.GetString(data);

                try
                {
                    SignalPayload payload = JsonUtility.FromJson<SignalPayload>(text);

                    if (payload != null && payload.signals != null)
                    {
                        lock (dataLock)
                        {
                            latestPayload = payload;
                        }
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning("Failed to parse TLS JSON: " + e.Message);
                }
            }
        }
        catch (Exception err)
        {
            if (isRunning)
            {
                Debug.LogError("UDP receive thread error (TLS): " + err.ToString());
            }
        }
    }

    void Update()
    {
        SignalPayload payload = null;

        lock (dataLock)
        {
            if (latestPayload != null)
            {
                payload = latestPayload;
                latestPayload = null; 
            }
        }

        if (payload != null && payload.signals != null)
        {
            foreach (SignalData sig in payload.signals)
            {
                GameObject tlsObj = GameObject.Find("TLS_" + sig.id);
                if (tlsObj != null)
                {
                    Renderer rnd = tlsObj.GetComponent<Renderer>();
                    if (rnd != null)
                    {
                        // SUMO state string: 'r' = red, 'y' = yellow, 'g' = green (and variations)
                        // If any part of the signal is green, show green.
                        // If no green but yellow, show yellow.
                        // Otherwise red.
                        string stateLower = sig.state.ToLower();
                        if (stateLower.Contains("g"))
                        {
                            rnd.material.color = Color.green;
                        }
                        else if (stateLower.Contains("y"))
                        {
                            rnd.material.color = Color.yellow;
                        }
                        else if (stateLower.Contains("r"))
                        {
                            rnd.material.color = Color.red;
                        }
                        else
                        {
                            rnd.material.color = Color.black; // unknown/off
                        }
                    }
                }
            }
            
            packetsReceived++;
            if (Time.time - lastLogTime >= 5.0f)
            {
                string firstPos = "None";
                string firstState = "UNKNOWN";
                
                if (payload.signals.Length > 0)
                {
                    SignalData firstSig = payload.signals[0];
                    GameObject tlsObj = GameObject.Find("TLS_" + firstSig.id);
                    if (tlsObj != null) firstPos = tlsObj.transform.position.ToString();
                    
                    string s = firstSig.state.ToLower();
                    if (s.Contains("g")) firstState = "GREEN";
                    else if (s.Contains("y")) firstState = "YELLOW";
                    else if (s.Contains("r")) firstState = "RED";
                }
                
                Debug.Log($"TrafficSignalReceiver: Packets received: {packetsReceived} | Signals updated: {payload.signals.Length}");
                Debug.Log($"Traffic signal visual check: Active signals = {payload.signals.Length} | First signal position = {firstPos} | First signal state = {firstState}");
                lastLogTime = Time.time;
            }
        }
    }

    void OnApplicationQuit()
    {
        isRunning = false;
        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Abort();
        }
        if (udpClient != null)
        {
            udpClient.Close();
        }
    }
}
