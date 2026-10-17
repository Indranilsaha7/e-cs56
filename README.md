# 🎙️ AirMic — Turn Your Android Phone into a High-Definition PC Microphone

**AirMic** is a high-performance, low-latency system consisting of two coordinated applications:
1. **Android App (`android_app`)**: Captures live 48.0kHz/44.1kHz 16-bit PCM microphone audio with hardware noise cancellation, volume boosting, phone IP auto-display, and real-time streaming over Wi-Fi (UDP/TCP) or USB.
2. **PC Receiver (`AirMic_Receiver.exe`)**: A **standalone, zero-dependency native Windows executable** (compiled with Rust, using Windows native `waveOut` audio engine). Requires **NO Python, NO runtime, NO setup**. Uses only 4 MB RAM and starts in 0.01 seconds.

---

## 🌟 Key Features

- **🚀 Ultra-Lightweight Native PC Receiver (`AirMic_Receiver.exe`)**:
  - Pure native Windows PE binary (~400 KB).
  - Uses Windows native `waveOut` (`winmm.dll`) for rock-solid audio playback without crashes.
  - Zero dependencies: runs out-of-the-box on Windows 10/11.
  - Real-time animated color VU meter bar with decibel readout in console.
- **🎙️ Upgraded 48kHz / 44.1kHz Audio Capture**:
  - Automatically targets Android's hardware native 48kHz sampling rate.
  - Uses direct `MediaRecorder.AudioSource.MIC` to prevent VoIP telephony attenuation or muting.
  - 8-byte `AMIC` protocol header for dynamic sample-rate negotiation.
- **📱 Phone IP Auto-Display & Subnet Matcher**:
  - The phone displays its active Wi-Fi IP and confirms whether it matches the PC's Wi-Fi router.
- **⚡ Two-Way Connect**:
  - Connect from Phone to PC via **"Search for PC on Wi-Fi"** or typing the PC IP.
  - Or trigger connection from PC by typing the Phone's IP.
- **Multi-Adapter Support**:
  - Intelligently detects and prioritizes the real physical Wi-Fi adapter (e.g. `192.168.0.103`), filtering out Hyper-V/WSL/Docker virtual switches (`172.31.64.1`).
- **Universal Windows Compatibility**:
  - Route sound to PC speakers for testing, or route to **VB-Audio Virtual Cable** to act as a system-wide microphone in Discord, Teams, Zoom, Valorant, CS2, etc.

---

## 📂 Project Structure

```
online mic/
├── AirMic_Receiver.exe            <-- Standalone Native PC Receiver (Zero dependencies!)
├── Start_PC_Receiver.bat          <-- 1-click launcher for PC Receiver
├── Fix_Firewall.bat               <-- 1-click allow UDP/TCP in Windows Firewall
├── Install_App_via_Wifi.bat       <-- 1-click download APK directly over Wi-Fi
├── Install_App_to_Phone.bat       <-- 1-click install APK to phone via USB
├── AirMic.apk                     <-- Pre-compiled Android APK (Root)
│
├── native_receiver/               <-- Rust source code for native Windows receiver
│   └── main.rs
│
├── pc_receiver/                   <-- Alternative Python/CustomTkinter GUI receiver
│   ├── app.py
│   ├── audio_engine.py
│   ├── network_server.py
│   └── requirements.txt
│
├── android_app/                   <-- Full Native Android Studio Project
│   ├── app/src/main/java/com/airmic/app/
│   │   ├── MainActivity.kt        <-- Phone UI, Phone IP detection, Subnet check
│   │   ├── MicService.kt          <-- Foreground Service + WakeLock & Notification
│   │   ├── AudioStreamer.kt       <-- 48kHz AudioRecord & AMIC UDP Streamer
│   │   └── NetworkDiscovery.kt    <-- Subnet broadcast scanner & beacon
│   ├── build.gradle.kts
│   └── gradlew.bat
│
├── install_vb_cable_guide.md      <-- Guide for Discord, Zoom, Games & OBS
└── README.md                      <-- Complete documentation
```

---

## 🚀 Quick Setup for Another PC (Your Brother's PC)

When you send this folder to your brother:

### Step 1: Allow Windows Firewall
On the brother's PC, right-click **`Fix_Firewall.bat`** and click **Run as administrator**. This ensures Windows Firewall won't block incoming phone audio packets on port 55555.

### Step 2: Launch the PC Receiver
Double-click **`Start_PC_Receiver.bat`** (or directly **`AirMic_Receiver.exe`**).
- It opens immediately in a lightweight console dashboard showing `192.168.0.103:55555`.
- It lists all output audio devices (Speakers, VB-Audio Cable). Press `0-9` to switch devices!
- Press `+` or `-` to adjust volume boost.

### Step 3: Install the Android App on the Phone
Either:
- Run **`Install_App_via_Wifi.bat`** on PC and open `http://192.168.0.103:8080/AirMic.apk` on phone browser.
- Or transfer **`AirMic.apk`** to the phone and tap to install.

### Step 4: Connect & Speak!
1. Open **AirMic** on the phone.
2. The phone will display its IP and confirm `✅ Both devices on same Wi-Fi subnet`.
3. Tap **`🎙️ START MICROPHONE`**!
4. The live VU meter on PC will jump immediately with your voice!

---

## 🎧 Using in Discord, Zoom, or Games

1. Install the free **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** (detailed in [`install_vb_cable_guide.md`](file:///c:/Users/Indranil%20saha/Desktop/coding/online%20mic/install_vb_cable_guide.md)).
2. In `AirMic_Receiver.exe`, select the number for **`CABLE Input (VB-Audio Virtual Cable)`**.
3. In Discord/Zoom audio settings, choose **`CABLE Output (VB-Audio Virtual Cable)`** as your Microphone!
