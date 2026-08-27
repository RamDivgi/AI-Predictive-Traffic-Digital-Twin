# 🚑 Unity ↔ SUMO Connection Setup

This guide details the setup required to run the first Unity 3D visualization milestone, streaming live coordinates from SUMO into a Unity GameObject via a lightweight UDP bridge.

## 🛠️ Unity Setup

1. **Open your existing Unity Project**: `D:\AIML\Projects\MangaluruDigitalTwin3D`
2. **Create the Script Folder** (if it doesn't exist): `Assets/Scripts/`
3. **Copy the Receiver Script**: 
   - Copy `D:\AIML\Projects\AI-Predictive-Traffic\visualization\AmbulanceReceiver.cs` into your Unity `Assets/Scripts/` folder.
   - Wait for Unity to compile the script (ensure there are no console errors).

## 🏙️ Required Scene Objects

Open or create a new Scene in Unity and ensure it contains exactly the following:

1. **Main Camera**: Positioned to look down at the ground (e.g., Position: `0, 5000, 0`, Rotation: `90, 0, 0`). *(Note: SUMO coordinates are very large, e.g. X=2692, Z=1431, so place the camera accordingly or track the object).*
2. **Directional Light**: For basic scene illumination.
3. **Ground**: 
   - Create a 3D Plane (`GameObject -> 3D Object -> Plane`).
   - Name it **"Ground"**.
   - Set Transform Position to `2500, 0, 1500` (roughly the center of the first coordinates).
   - Scale it up (e.g., `X: 500, Y: 1, Z: 500`) so you have a large surface.
4. **Ambulance**: 
   - Create a 3D Cube (`GameObject -> 3D Object -> Cube`).
   - Name it **"Ambulance"**.
   - Attach the `AmbulanceReceiver` script to this GameObject.

## 🚀 Startup Order & Testing

1. **Start Unity**: 
   - Press the **Play** button in the Unity Editor.
   - In the Unity Console, you should immediately see: `AmbulanceReceiver: Started UDP listener on port 5005`.
   - The scene will wait for data.

2. **Start the Python Bridge**:
   - Open a terminal and navigate to your Python project directory: `D:\AIML\Projects\AI-Predictive-Traffic`.
   - Run the bridge script:
     ```bash
     python visualization/unity_bridge.py
     ```
   - This script automatically starts the existing SUMO `ambulance_test.sumocfg` scenario using TraCI. *Do not start SUMO manually.*

3. **Verify the Connection**:
   - In the Python terminal, you should see it find the ambulance and start streaming coordinates: `Step 100 | SUMO(X:..., Y:...) -> Unity(X:..., Z:...)`.
   - Switch back to Unity. Look at the Unity Console. You should see a message every 2 seconds: `Ambulance position received. Unity position: X=..., Y=0.00, Z=...`.
   - **Visual Verification**: The "Ambulance" Cube should smoothly move across the "Ground" plane!

## 🔧 Troubleshooting

- **No movement in Unity**: Ensure the Python script is running and printing coordinates. If it prints but Unity doesn't move, check if a firewall is blocking local UDP port `5005`.
- **Unity Console Errors**: Ensure the JSON structure exactly matches the `TelemetryData` class in C#.
- **Stuttering Movement**: The Python bridge steps SUMO and sends data roughly 20 times per second (`time.sleep(0.05)`). Unity interpolates the transforms to smooth this out. If it stutters, you can tweak the `movementSmoothing` public variable on the script in the Unity Inspector.
