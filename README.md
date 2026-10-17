# 🎙️ AirMic — Turn Your Android Phone into a High-Definition PC Microphone

**AirMic** is a high-performance, low-latency system consisting of two coordinated applications:
1. **Android App (`android_app`)**: Captures live 44.1kHz 16-bit PCM microphone audio with hardware noise cancellation, volume boosting, phone IP auto-display, and real-time streaming over Wi-Fi (UDP/TCP) or USB.
2. **PC Receiver (`pc_receiver`)**: A Windows desktop application with a modern dark-mode GUI, live decibel VU meter, low-latency WASAPI audio engine, one-click USB ADB bridge, virtual microphone routing for Discord/Zoom/Games, and remote Phone IP triggering.

---

## 🌟 Key Features

- **Ultra-Low Latency (~12ms - 23ms)**: High-speed UDP streaming engineered for gaming and live voice chats.
- **📱 Phone IP Auto-Display & Subnet Matcher**: The phone screen shows its own active Wi-Fi IP and confirms whether it matches the PC's Wi-Fi router.
- **🚀 Two-Way Connect**:
  - Connect from Phone to PC via **"Search for PC on Wi-Fi"** or typing the PC IP.
  - Or connect from PC to Phone by entering the Phone's IP and clicking **"Trigger Phone"**.
- **Multi-Adapter Support**: Intelligently handles PCs with Hyper-V, WSL, or Docker virtual switches (like `172.31.64.1`) by automatically detecting and prioritizing the real physical Wi-Fi adapter (e.g. `192.168.0.103`).
- **USB Cable Support**: Works over standard USB cable with zero Wi-Fi interference via built-in 1-click ADB port forwarding.
- **Hardware Noise Cancellation**: Leverages your phone's built-in `NoiseSuppressor` and `AcousticEchoCanceler` DSPs.
- **Live Sound Visualizer**: Real-time VU meter with dB meter on both the phone and PC screens.
- **Volume Booster / Gain Control**: Boost microphone sensitivity from 10% to 300% with soft-clipping protection.
- **Background Foreground Service**: Audio continues streaming reliably even when the phone's screen is locked or another app is open.
- **Universal Windows Compatibility**: Route sound to PC speakers for testing, or route to **VB-Audio Virtual Cable** to act as a system-wide microphone in Discord, Teams, Zoom, Valorant, CS2, etc.

---

## 📂 Project Structure

```
online mic/
├── Start_PC_Receiver.bat          <-- Double-click to launch PC Receiver
├── Fix_Firewall.bat               <-- 1-click allow UDP/TCP in Windows Firewall
├── Install_App_to_Phone.bat       <-- 1-click install APK to phone via USB
├── apk/
│   └── AirMic.apk                 <-- Pre-compiled Android APK (Ready to install)
│
├── pc_receiver/                   <-- Windows Desktop Application
│   ├── app.py                     <-- Modern CustomTkinter Dark GUI
│   ├── audio_engine.py            <-- Low-latency WASAPI/MME Sound Engine + VU Meter
│   ├── network_server.py          <-- UDP/TCP Server + Phone Triggering + Discovery
│   ├── usb_bridge.py              <-- ADB USB Port Forwarding Bridge
│   ├── requirements.txt           <-- Python dependencies
│   └── run_pc_mic.bat             <-- Windows launcher
│
├── android_app/                   <-- Full Native Android Studio Project
│   ├── app/src/main/java/com/airmic/app/
│   │   ├── MainActivity.kt        <-- Phone UI, Phone IP detection, Subnet check
│   │   ├── MicService.kt          <-- Foreground Service + WakeLock & Notification
│   │   ├── AudioStreamer.kt       <-- 44.1kHz 16-bit PCM AudioRecord & UDP Streamer
│   │   └── NetworkDiscovery.kt    <-- Subnet broadcast scanner & beacon
│   ├── build.gradle.kts           <-- Gradle build configuration
│   └── gradlew.bat
│
├── install_vb_cable_guide.md      <-- Guide for Discord, Zoom, Games & OBS
└── README.md                      <-- Complete documentation
```

---

## 🚀 Quick Setup for Another PC (Your Brother's PC)

When you send this folder to your brother:

### Step 1: Allow Windows Firewall (Important!)
On the brother's PC, right-click **`Fix_Firewall.bat`** and click **Run as administrator** (or click the button in the app). This guarantees Windows Firewall won't block incoming phone audio packets on port 55555.

### Step 2: Launch the PC Receiver
Double-click **`Start_PC_Receiver.bat`**.
- It will automatically detect Python, install the packages, and open the AirMic desktop receiver.
- Under **PC Network Interface**, it will automatically pick **`192.168.0.103 (Wi-Fi)`** (ignoring virtual switches like Hyper-V `172.31.64.1`).

### Step 3: Install the Android App on the Phone
Send **`apk\AirMic.apk`** to the phone (via WhatsApp, Google Drive, or USB) and tap to install it.
*(Or plug the phone into the PC with USB debugging and double-click `Install_App_to_Phone.bat`)*.

### Step 4: Connect & Speak!
1. Open **AirMic** on the phone.
2. The phone will show:
   - **`📱 My Phone Wi-Fi IP: 192.168.0.X`**
   - **`✅ Both devices on same Wi-Fi subnet (192.168.0.x)`**
3. Tap **`🔍 Search for PC on Wi-Fi`** (or leave `192.168.0.103` in the box) and tap **`🎙️ START MICROPHONE`**!
   *(Alternatively, on the PC type the phone's IP into "Phone IP" and click "🚀 Trigger Phone")*.
4. Speak into your phone — both screens will show the green VU meter jumping in real time!

---

## 🎧 Using as a Real Microphone in Discord / Zoom / Games

To route your phone audio into Discord, Zoom, OBS, or Windows:
1. Install the free **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** (detailed in [`install_vb_cable_guide.md`](file:///c:/Users/Indranil%20saha/Desktop/coding/online%20mic/install_vb_cable_guide.md)).
2. In the AirMic PC Receiver under **Audio Routing Target**, select:
   👉 **`⭐ [VIRTUAL MIC] CABLE Input (VB-Audio Virtual Cable)`**
3. In Discord/Zoom/Game audio settings, choose **`CABLE Output (VB-Audio Virtual Cable)`** as your Microphone.
