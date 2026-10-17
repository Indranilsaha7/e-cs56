#![allow(non_snake_case)]
#![allow(unused_imports)]

use std::collections::VecDeque;
use std::io::{self, stdout, Read, Write};
use std::net::{SocketAddr, UdpSocket};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

// ------------------ Windows Multimedia API Definitions ------------------

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct WAVEFORMATEX {
    pub wFormatTag: u16,
    pub nChannels: u16,
    pub nSamplesPerSec: u32,
    pub nAvgBytesPerSec: u32,
    pub nBlockAlign: u16,
    pub wBitsPerSample: u16,
    pub cbSize: u16,
}

#[repr(C)]
#[derive(Debug)]
pub struct WAVEHDR {
    pub lpData: *mut u8,
    pub dwBufferLength: u32,
    pub dwBytesRecorded: u32,
    pub dwUser: usize,
    pub dwFlags: u32,
    pub dwLoops: u32,
    pub lpNext: *mut WAVEHDR,
    pub reserved: usize,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct WAVEOUTCAPSA {
    pub wMid: u16,
    pub wPid: u16,
    pub vDriverVersion: u32,
    pub szPname: [u8; 32],
    pub dwFormats: u32,
    pub wChannels: u16,
    pub wReserved1: u16,
    pub dwSupport: u32,
}

const WAVE_MAPPER: usize = usize::MAX;
const WAVE_FORMAT_PCM: u16 = 1;
const WHDR_DONE: u32 = 0x00000001;
const WHDR_PREPARED: u32 = 0x00000002;

#[link(name = "winmm")]
extern "system" {
    pub fn waveOutGetNumDevs() -> u32;
    pub fn waveOutGetDevCapsA(uDeviceID: usize, pwoc: *mut WAVEOUTCAPSA, cbwoc: u32) -> u32;
    pub fn waveOutOpen(
        phwo: *mut isize,
        uDeviceID: usize,
        pwfx: *const WAVEFORMATEX,
        dwCallback: usize,
        dwInstance: usize,
        fdwOpen: u32,
    ) -> u32;
    pub fn waveOutPrepareHeader(hwo: isize, pwh: *mut WAVEHDR, cbwh: u32) -> u32;
    pub fn waveOutWrite(hwo: isize, pwh: *mut WAVEHDR, cbwh: u32) -> u32;
    pub fn waveOutUnprepareHeader(hwo: isize, pwh: *mut WAVEHDR, cbwh: u32) -> u32;
    pub fn waveOutReset(hwo: isize) -> u32;
    pub fn waveOutClose(hwo: isize) -> u32;
}

// ------------------ Audio Device Struct ------------------

#[derive(Clone, Debug)]
pub struct AudioDevice {
    pub index: usize,
    pub name: String,
    pub is_vb_cable: bool,
}

pub fn list_audio_devices() -> Vec<AudioDevice> {
    let mut devices = Vec::new();
    let num_devs = unsafe { waveOutGetNumDevs() };

    for i in 0..num_devs as usize {
        let mut caps: WAVEOUTCAPSA = unsafe { std::mem::zeroed() };
        unsafe {
            waveOutGetDevCapsA(i, &mut caps, std::mem::size_of::<WAVEOUTCAPSA>() as u32);
        }
        let name_bytes: Vec<u8> = caps.szPname.iter().take_while(|&&b| b != 0).cloned().collect();
        let name = String::from_utf8_lossy(&name_bytes).to_string();
        let is_vb_cable = name.to_lowercase().contains("cable") || name.to_lowercase().contains("vb-audio");
        devices.push(AudioDevice {
            index: i,
            name,
            is_vb_cable,
        });
    }
    devices
}

// ------------------ Native WaveOut Player ------------------

const BUFFER_COUNT: usize = 8;
const BUFFER_SAMPLES: usize = 1024; // 1024 stereo samples = 2048 i16 = 4096 bytes per buffer

struct WaveBuffer {
    header: WAVEHDR,
    data: Vec<u8>,
}

pub struct WavePlayer {
    hwo: isize,
    device_id: usize,
    sample_rate: u32,
    buffers: Vec<WaveBuffer>,
    current_buf: usize,
}

impl WavePlayer {
    pub fn new(device_id: usize, sample_rate: u32) -> Result<Self, String> {
        let wfx = WAVEFORMATEX {
            wFormatTag: WAVE_FORMAT_PCM,
            nChannels: 2, // Stereo output for 100% Windows endpoint compatibility
            nSamplesPerSec: sample_rate,
            nAvgBytesPerSec: sample_rate * 2 * 2, // sample_rate * 2 channels * 2 bytes
            nBlockAlign: 4,
            wBitsPerSample: 16,
            cbSize: 0,
        };

        let mut hwo: isize = 0;
        let res = unsafe {
            waveOutOpen(
                &mut hwo,
                device_id,
                &wfx,
                0, // No callback function (polled headers)
                0,
                0,
            )
        };

        if res != 0 || hwo == 0 {
            return Err(format!("waveOutOpen failed with error code: {}", res));
        }

        let buffer_bytes = BUFFER_SAMPLES * 4; // 1024 stereo samples * 4 bytes
        let mut buffers = Vec::with_capacity(BUFFER_COUNT);

        for _ in 0..BUFFER_COUNT {
            let mut data = vec![0u8; buffer_bytes];
            let header = WAVEHDR {
                lpData: data.as_mut_ptr(),
                dwBufferLength: buffer_bytes as u32,
                dwBytesRecorded: 0,
                dwUser: 0,
                dwFlags: 0,
                dwLoops: 0,
                lpNext: std::ptr::null_mut(),
                reserved: 0,
            };
            buffers.push(WaveBuffer { header, data });
        }

        Ok(WavePlayer {
            hwo,
            device_id,
            sample_rate,
            buffers,
            current_buf: 0,
        })
    }

    pub fn write_stereo_pcm(&mut self, stereo_bytes: &[u8]) {
        let buf_idx = self.current_buf;
        let wb = &mut self.buffers[buf_idx];

        // Wait if buffer is still playing
        if (wb.header.dwFlags & WHDR_PREPARED) != 0 {
            while (wb.header.dwFlags & WHDR_DONE) == 0 {
                thread::sleep(Duration::from_millis(1));
            }
            unsafe {
                waveOutUnprepareHeader(self.hwo, &mut wb.header, std::mem::size_of::<WAVEHDR>() as u32);
            }
        }

        let copy_len = stereo_bytes.len().min(wb.data.len());
        wb.data[..copy_len].copy_from_slice(&stereo_bytes[..copy_len]);
        if copy_len < wb.data.len() {
            wb.data[copy_len..].fill(0);
        }

        wb.header.dwBufferLength = copy_len as u32;
        wb.header.dwFlags = 0;

        unsafe {
            waveOutPrepareHeader(self.hwo, &mut wb.header, std::mem::size_of::<WAVEHDR>() as u32);
            waveOutWrite(self.hwo, &mut wb.header, std::mem::size_of::<WAVEHDR>() as u32);
        }

        self.current_buf = (self.current_buf + 1) % BUFFER_COUNT;
    }

    pub fn close(&mut self) {
        if self.hwo != 0 {
            unsafe {
                waveOutReset(self.hwo);
                for wb in &mut self.buffers {
                    if (wb.header.dwFlags & WHDR_PREPARED) != 0 {
                        waveOutUnprepareHeader(self.hwo, &mut wb.header, std::mem::size_of::<WAVEHDR>() as u32);
                    }
                }
                waveOutClose(self.hwo);
            }
            self.hwo = 0;
        }
    }
}

impl Drop for WavePlayer {
    fn drop(&mut self) {
        self.close();
    }
}

// ------------------ Shared State & Network ------------------

struct AppState {
    running: AtomicBool,
    gain_pct: AtomicU32, // e.g. 100 = 1.0x, 200 = 2.0x
    is_muted: AtomicBool,
    current_level_pct: AtomicU32, // 0 to 100 for VU meter
    current_db_scaled: AtomicU32, // absolute dB * 10
    total_bytes: AtomicU32,
    last_phone_ip: Mutex<Option<String>>,
    active_device_idx: AtomicU32,
    active_sample_rate: AtomicU32,
}

fn detect_lan_ips() -> Vec<String> {
    let mut ips = Vec::new();
    // UDP connect probe
    if let Ok(s) = UdpSocket::bind("0.0.0.0:0") {
        if s.connect("8.8.8.8:80").is_ok() {
            if let Ok(addr) = s.local_addr() {
                let ip = addr.ip().to_string();
                if !ip.starts_with("127.") {
                    ips.push(ip);
                }
            }
        }
    }
    if ips.is_empty() {
        ips.push("192.168.0.103".to_string());
    }
    ips
}

fn calculate_subnet_broadcast(ip: &str) -> String {
    let parts: Vec<&str> = ip.split('.').collect();
    if parts.len() == 4 {
        format!("{}.{}.{}.255", parts[0], parts[1], parts[2])
    } else {
        "255.255.255.255".to_string()
    }
}

// ------------------ Main Application ------------------

fn main() {
    // Enable ANSI escape sequence colors in Windows Console
    let _ = enable_virtual_terminal_processing();

    let devices = list_audio_devices();
    if devices.is_empty() {
        println!("❌ Error: No audio output devices found on this PC!");
        return;
    }

    // Default: choose VB-CABLE if found, else device 0
    let default_device = devices
        .iter()
        .find(|d| d.is_vb_cable)
        .map(|d| d.index)
        .unwrap_or(0);

    let lan_ips = detect_lan_ips();
    let primary_ip = lan_ips[0].clone();

    let state = Arc::new(AppState {
        running: AtomicBool::new(true),
        gain_pct: AtomicU32::new(100),
        is_muted: AtomicBool::new(false),
        current_level_pct: AtomicU32::new(0),
        current_db_scaled: AtomicU32::new(600), // -60.0 dB
        total_bytes: AtomicU32::new(0),
        last_phone_ip: Mutex::new(None),
        active_device_idx: AtomicU32::new(default_device as u32),
        active_sample_rate: AtomicU32::new(48000), // Default 48kHz native
    });

    println!("\x1b[2J\x1b[H"); // Clear screen

    // 1. Audio Processing & Playback Thread
    let (pcm_tx, pcm_rx) = std::sync::mpsc::sync_channel::<Vec<u8>>(128);
    let state_audio = Arc::clone(&state);

    let audio_thread = thread::spawn(move || {
        let mut current_rate = 48000u32;
        let mut current_dev = state_audio.active_device_idx.load(Ordering::Relaxed) as usize;
        let mut player = match WavePlayer::new(current_dev, current_rate) {
            Ok(p) => Some(p),
            Err(e) => {
                eprintln!("\n⚠️ Failed to open waveOut on device {}: {}", current_dev, e);
                None
            }
        };

        let mut stereo_buf = Vec::with_capacity(4096);

        while state_audio.running.load(Ordering::Relaxed) {
            // Check if device or sample rate changed
            let target_dev = state_audio.active_device_idx.load(Ordering::Relaxed) as usize;
            let target_rate = state_audio.active_sample_rate.load(Ordering::Relaxed);

            if target_dev != current_dev || target_rate != current_rate || player.is_none() {
                if let Some(ref mut p) = player {
                    p.close();
                }
                current_dev = target_dev;
                current_rate = target_rate;
                player = WavePlayer::new(current_dev, current_rate).ok();
            }

            match pcm_rx.recv_timeout(Duration::from_millis(100)) {
                Ok(raw_pcm) => {
                    if raw_pcm.len() < 2 {
                        continue;
                    }

                    let gain = state_audio.gain_pct.load(Ordering::Relaxed) as f32 / 100.0;
                    let is_muted = state_audio.is_muted.load(Ordering::Relaxed);

                    // Convert bytes to i16 samples
                    let sample_count = raw_pcm.len() / 2;
                    let mut sum_squares = 0.0f64;

                    stereo_buf.clear();
                    stereo_buf.reserve(sample_count * 4);

                    for i in 0..sample_count {
                        let sample_raw = i16::from_le_bytes([raw_pcm[i * 2], raw_pcm[i * 2 + 1]]);
                        sum_squares += (sample_raw as f64) * (sample_raw as f64);

                        let out_sample = if is_muted {
                            0i16
                        } else if (gain - 1.0).abs() < 0.01 {
                            sample_raw
                        } else {
                            // Apply Gain with soft-clipping protection
                            let scaled = (sample_raw as f32) * gain;
                            scaled.clamp(-32767.0, 32767.0) as i16
                        };

                        // Duplicate mono -> stereo
                        let bytes = out_sample.to_le_bytes();
                        stereo_buf.push(bytes[0]);
                        stereo_buf.push(bytes[1]);
                        stereo_buf.push(bytes[0]);
                        stereo_buf.push(bytes[1]);
                    }

                    // Calculate RMS and Decibels
                    let rms = (sum_squares / sample_count as f64).sqrt();
                    let ratio = (rms / 32768.0).clamp(1e-5, 1.0);
                    let db = (20.0 * ratio.log10()) as f32; // -60.0 to 0.0 dB
                    let pct = (((db + 50.0) / 50.0) * 100.0).clamp(0.0, 100.0) as u32;

                    state_audio.current_level_pct.store(if is_muted { 0 } else { pct }, Ordering::Relaxed);
                    state_audio.current_db_scaled.store(
                        if is_muted { 900 } else { (-db * 10.0) as u32 },
                        Ordering::Relaxed,
                    );

                    // Write to Windows waveOut
                    if let Some(ref mut p) = player {
                        p.write_stereo_pcm(&stereo_buf);
                    }
                }
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                    // Decay level
                    let cur = state_audio.current_level_pct.load(Ordering::Relaxed);
                    state_audio.current_level_pct.store((cur as f32 * 0.7) as u32, Ordering::Relaxed);
                }
                Err(_) => break,
            }
        }
    });

    // 2. UDP Audio Receiver Thread (Port 55555)
    let state_net = Arc::clone(&state);
    let pcm_sender = pcm_tx.clone();

    thread::spawn(move || {
        let socket = match UdpSocket::bind("0.0.0.0:55555") {
            Ok(s) => s,
            Err(e) => {
                eprintln!("❌ Error binding UDP port 55555: {}. (Is another instance running?)", e);
                return;
            }
        };

        let mut buf = [0u8; 4096];

        while state_net.running.load(Ordering::Relaxed) {
            match socket.recv_from(&mut buf) {
                Ok((len, src)) => {
                    if len == 0 {
                        continue;
                    }

                    // Store client IP
                    let src_ip = src.ip().to_string();
                    {
                        let mut last = state_net.last_phone_ip.lock().unwrap();
                        if last.as_deref() != Some(&src_ip) {
                            *last = Some(src_ip);
                        }
                    }

                    state_net.total_bytes.fetch_add(len as u32, Ordering::Relaxed);

                    // Check for 8-byte header: "AMIC" [u16 rate] [u8 ch] [u8 flags]
                    if len > 8 && &buf[0..4] == b"AMIC" {
                        let sample_rate = u16::from_le_bytes([buf[4], buf[5]]) as u32;
                        if sample_rate == 48000 || sample_rate == 44100 || sample_rate == 16000 {
                            state_net.active_sample_rate.store(sample_rate, Ordering::Relaxed);
                        }
                        let _ = pcm_sender.try_send(buf[8..len].to_vec());
                    } else {
                        // Raw PCM
                        let _ = pcm_sender.try_send(buf[0..len].to_vec());
                    }
                }
                Err(_) => thread::sleep(Duration::from_millis(5)),
            }
        }
    });

    // 3. UDP Discovery Beacon & Responder Thread (Port 55554)
    let state_disc = Arc::clone(&state);
    let pc_ip_copy = primary_ip.clone();

    thread::spawn(move || {
        let socket = match UdpSocket::bind("0.0.0.0:55554") {
            Ok(s) => {
                let _ = s.set_broadcast(true);
                let _ = s.set_read_timeout(Some(Duration::from_millis(1000)));
                s
            }
            Err(_) => return,
        };

        let subnet_bcast = calculate_subnet_broadcast(&pc_ip_copy);
        let mut last_beacon = Instant::now();
        let mut buf = [0u8; 1024];

        while state_disc.running.load(Ordering::Relaxed) {
            // Listen for probe
            if let Ok((len, src)) = socket.recv_from(&mut buf) {
                let text = String::from_utf8_lossy(&buf[..len]);
                if text.contains("AIRMIC") && text.contains("DISCOVER") {
                    let reply = format!(
                        r#"{{"protocol":"AIRMIC","type":"BEACON","ip":"{}","audio_port":55555,"pc_name":"AirMic-PC"}}"#,
                        pc_ip_copy
                    );
                    let _ = socket.send_to(reply.as_bytes(), src);
                }
            }

            // Periodic broadcast every 2s
            if last_beacon.elapsed() >= Duration::from_secs(2) {
                last_beacon = Instant::now();
                let beacon = format!(
                    r#"{{"protocol":"AIRMIC","type":"BEACON","ip":"{}","audio_port":55555,"pc_name":"AirMic-PC"}}"#,
                    pc_ip_copy
                );
                let _ = socket.send_to(beacon.as_bytes(), "255.255.255.255:55554");
                let _ = socket.send_to(beacon.as_bytes(), format!("{}:55554", subnet_bcast));
            }
        }
    });

    // 4. Live UI Render Loop & Keyboard Input
    let state_ui = Arc::clone(&state);

    // Keyboard listener in separate thread
    let state_key = Arc::clone(&state);
    let dev_count = devices.len();
    let prim_ip_for_key = primary_ip.clone();

    thread::spawn(move || {
        loop {
            let mut input = [0u8; 1];
            if io::stdin().read_exact(&mut input).is_ok() {
                let ch = input[0] as char;
                match ch {
                    'q' | 'Q' => {
                        state_key.running.store(false, Ordering::Relaxed);
                        break;
                    }
                    'm' | 'M' => {
                        let cur = state_key.is_muted.load(Ordering::Relaxed);
                        state_key.is_muted.store(!cur, Ordering::Relaxed);
                    }
                    '+' | '=' => {
                        let cur = state_key.gain_pct.load(Ordering::Relaxed);
                        if cur < 300 {
                            state_key.gain_pct.store(cur + 10, Ordering::Relaxed);
                        }
                    }
                    '-' | '_' => {
                        let cur = state_key.gain_pct.load(Ordering::Relaxed);
                        if cur > 10 {
                            state_key.gain_pct.store(cur - 10, Ordering::Relaxed);
                        }
                    }
                    '0'..='9' => {
                        let idx = (ch as u8 - b'0') as usize;
                        if idx < dev_count {
                            state_key.active_device_idx.store(idx as u32, Ordering::Relaxed);
                        }
                    }
                    't' | 'T' => {
                        // Send trigger to last known phone IP
                        let maybe_phone = state_key.last_phone_ip.lock().unwrap().clone();
                        if let Some(phone_ip) = maybe_phone {
                            if let Ok(s) = UdpSocket::bind("0.0.0.0:0") {
                                let trigger = format!(
                                    r#"{{"protocol":"AIRMIC","type":"CONNECT_REQUEST","pc_ip":"{}","port":55555}}"#,
                                    prim_ip_for_key
                                );
                                let _ = s.send_to(trigger.as_bytes(), format!("{}:55554", phone_ip));
                            }
                        }
                    }
                    'f' | 'F' => {
                        // Launch firewall script
                        let _ = std::process::Command::new("cmd.exe")
                            .args(&["/c", "Fix_Firewall.bat"])
                            .spawn();
                    }
                    _ => {}
                }
            }
        }
    });

    // Render loop
    let mut last_bytes = 0u32;
    let mut last_kbps = 0.0f32;
    let mut last_stat_time = Instant::now();

    while state_ui.running.load(Ordering::Relaxed) {
        thread::sleep(Duration::from_millis(50));

        // Throughput calculation
        if last_stat_time.elapsed() >= Duration::from_millis(500) {
            let elapsed_sec = last_stat_time.elapsed().as_secs_f32();
            let cur_bytes = state_ui.total_bytes.load(Ordering::Relaxed);
            let diff = cur_bytes.saturating_sub(last_bytes);
            last_kbps = (diff as f32 * 8.0) / (elapsed_sec * 1000.0);
            last_bytes = cur_bytes;
            last_stat_time = Instant::now();
        }

        let phone_ip = state_ui.last_phone_ip.lock().unwrap().clone();
        let is_connected = phone_ip.is_some() && last_kbps > 5.0;
        let gain = state_ui.gain_pct.load(Ordering::Relaxed);
        let is_muted = state_ui.is_muted.load(Ordering::Relaxed);
        let level_pct = state_ui.current_level_pct.load(Ordering::Relaxed);
        let db_val = -(state_ui.current_db_scaled.load(Ordering::Relaxed) as f32) / 10.0;
        let active_dev = state_ui.active_device_idx.load(Ordering::Relaxed) as usize;
        let sample_rate = state_ui.active_sample_rate.load(Ordering::Relaxed);

        // Draw Terminal UI
        print!("\x1b[H"); // Cursor to home

        println!("\x1b[1;36m╔════════════════════════════════════════════════════════════════════════════╗\x1b[0m");
        println!("\x1b[1;36m║               🎙️  AirMic Native Windows PC Receiver                        ║\x1b[0m");
        println!("\x1b[1;36m║         Ultra-Lightweight • Zero Dependencies • Native WaveOut             ║\x1b[0m");
        println!("\x1b[1;36m╚════════════════════════════════════════════════════════════════════════════╝\x1b[0m");
        println!();

        // Status Line
        if is_connected {
            let ip_str = phone_ip.as_deref().unwrap_or("Phone");
            println!(
                " \x1b[1;32m● STREAMING LIVE\x1b[0m from \x1b[1;37m{}\x1b[0m (\x1b[36m{} Hz\x1b[0m • \x1b[33m{:.1} kbps\x1b[0m)",
                ip_str, sample_rate, last_kbps
            );
        } else {
            println!(
                " \x1b[1;33m● LISTENING\x1b[0m on \x1b[1;37m{}:55555\x1b[0m (Open AirMic app on phone)",
                primary_ip
            );
        }

        println!();

        // VU Meter Bar (40 characters)
        let bar_len = 40;
        let filled = ((level_pct as f32 / 100.0) * bar_len as f32) as usize;
        let mut bar = String::new();

        for i in 0..bar_len {
            if i < filled {
                if i < 24 {
                    bar.push_str("\x1b[1;32m█\x1b[0m"); // Green
                } else if i < 34 {
                    bar.push_str("\x1b[1;33m█\x1b[0m"); // Yellow
                } else {
                    bar.push_str("\x1b[1;31m█\x1b[0m"); // Red
                }
            } else {
                bar.push_str("\x1b[90m░\x1b[0m");
            }
        }

        if is_muted {
            println!(" Mic Level:  [{}] \x1b[1;31mMUTED\x1b[0m                 ", bar);
        } else if db_val > -55.0 {
            println!(" Mic Level:  [{}] \x1b[1;37m{:>5.1} dB\x1b[0m             ", bar, db_val);
        } else {
            println!(" Mic Level:  [{}] \x1b[90m -∞  dB\x1b[0m             ", bar);
        }

        println!(" Gain Boost: \x1b[1;36m{}%\x1b[0m (Press [+] or [-] to adjust)   ", gain);
        println!();

        // Audio Devices Table
        println!("\x1b[1;37m🔊 Audio Routing Targets:\x1b[0m");
        for dev in &devices {
            let is_selected = dev.index == active_dev;
            let star = if is_selected { "\x1b[1;32m► \x1b[0m" } else { "  " };
            let cable_tag = if dev.is_vb_cable { " \x1b[1;33m[VIRTUAL MIC FOR DISCORD/ZOOM]\x1b[0m" } else { "" };
            println!(
                "{} [{}] {}{}\x1b[K",
                star, dev.index, dev.name, cable_tag
            );
        }

        println!();
        println!("\x1b[90m─────────────────────────────────────────────────────────────────────────────\x1b[0m");
        println!("\x1b[1;37mCommands:\x1b[0m [0-9] Select Output | [+] Boost | [-] Reduce | [M] Mute | [T] Trigger Phone | [F] Firewall | [Q] Quit\x1b[K");

        let _ = stdout().flush();
    }

    println!("\n👋 AirMic Receiver closed cleanly.");
    let _ = audio_thread.join();
}

// Helper to enable ANSI escape sequences on Windows console
fn enable_virtual_terminal_processing() -> Result<(), ()> {
    #[link(name = "kernel32")]
    extern "system" {
        fn GetStdHandle(nStdHandle: u32) -> isize;
        fn GetConsoleMode(hConsoleHandle: isize, lpMode: *mut u32) -> i32;
        fn SetConsoleMode(hConsoleHandle: isize, dwMode: u32) -> i32;
    }
    const STD_OUTPUT_HANDLE: u32 = 0xFFFFFFF5; // -11
    const ENABLE_VIRTUAL_TERMINAL_PROCESSING: u32 = 0x0004;

    unsafe {
        let handle = GetStdHandle(STD_OUTPUT_HANDLE);
        if handle == 0 || handle == -1 {
            return Err(());
        }
        let mut mode: u32 = 0;
        if GetConsoleMode(handle, &mut mode) == 0 {
            return Err(());
        }
        mode |= ENABLE_VIRTUAL_TERMINAL_PROCESSING;
        if SetConsoleMode(handle, mode) == 0 {
            return Err(());
        }
    }
    Ok(())
}
