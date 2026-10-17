# How to Use AirMic as a System-Wide Windows Microphone

By default, the **AirMic PC Receiver** can play your phone's microphone sound directly through your PC's speakers or headphones so you can hear yourself.

However, to use your phone as a **real microphone** inside apps like:
- **Discord**
- **Zoom / Google Meet / Microsoft Teams**
- **OBS Studio**
- **Steam / In-Game Voice Chats (Valorant, CS2, Fortnite, etc.)**
- **Audacity / FL Studio**

Windows requires a **Virtual Audio Device**. The standard and free solution used by millions of streamers and gamers is **VB-Audio Virtual Cable**.

---

## 3 Simple Steps to Set Up VB-Audio Virtual Cable

### Step 1: Download & Install VB-CABLE (Free)
1. Download the official free driver from: [https://vb-audio.com/Cable/](https://vb-audio.com/Cable/)
2. Extract the downloaded `.zip` file.
3. Right-click **`VBCABLE_Setup_x64.exe`** and select **Run as administrator**.
4. Click **Install Driver**, then restart your PC (or restart the audio service).

---

### Step 2: Configure the AirMic PC Receiver
1. Launch **AirMic PC Receiver** (`run_pc_mic.bat`).
2. Under **Audio Routing Target**, select:
   👉 **`⭐ [VIRTUAL MIC] CABLE Input (VB-Audio Virtual Cable)`**
3. AirMic will now pump your phone's microphone audio straight into the virtual cable.

---

### Step 3: Select the Microphone in Your Favorite App
Now open any voice app and set your input device:

- **Discord**:
  `Settings` > `Voice & Video` > `Input Device` > select **`CABLE Output (VB-Audio Virtual Cable)`**.
- **Zoom**:
  `Settings` > `Audio` > `Microphone` > select **`CABLE Output (VB-Audio Virtual Cable)`**.
- **Windows Default Mic (Whole PC)**:
  `Windows Settings` > `System` > `Sound` > `Input` > select **`CABLE Output (VB-Audio Virtual Cable)`**.

---

### Pro-Tips:
- **Listen to Yourself / Testing**:
  In the AirMic PC Receiver, simply click **`🎧 Listen to Myself (On)`** to temporarily route audio to your headphones to test your mic clarity and volume.
- **Latency**:
  Set the latency profile in the PC app to **Balanced (~23ms)** or **Ultra Low (~12ms)** for gaming and real-time talk.
- **Volume Boost**:
  Use the **Mic Gain / Boost** slider in the PC app or Android app if your voice needs extra amplification.
