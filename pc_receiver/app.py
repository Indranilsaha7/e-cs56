"""
AirMic PC Receiver - Modern Desktop GUI
Built with CustomTkinter for a sleek Windows 11 dark-mode experience.
Includes Network Interface Selection, Phone IP Remote Triggering,
Live Decibel VU Meter, and Virtual Audio Cable routing.
"""

import customtkinter as ctk
import os
import subprocess
import sys
import threading
import time
import webbrowser

from audio_engine import AudioEngine
from network_server import NetworkServer
from usb_bridge import USBBridge


class AirMicApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("AirMic — Phone to PC Microphone")
        self.geometry("740x860")
        self.minsize(700, 780)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Audio & Network instances
        self.audio_engine = AudioEngine()
        self.network_server = NetworkServer(
            on_audio_chunk=self.audio_engine.push_pcm_data,
            on_status_change=self.on_network_status_change
        )

        self.devices = []
        self.selected_device_idx = None
        self.is_monitoring_self = False

        # Load Network Interfaces
        self.interfaces = NetworkServer.get_lan_interfaces()
        self.active_pc_ip = self.interfaces[0]['ip'] if self.interfaces else "127.0.0.1"
        self.network_server.set_active_ip(self.active_pc_ip)

        # Build UI layout
        self._build_ui()

        # Start Services
        self._start_services()

        # Update loop for VU meter and statistics
        self.after(33, self._ui_update_loop)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _build_ui(self):
        # Main scrollable container
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=15)

        # Header Title & Subtitle
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🎙️ AirMic PC Receiver",
            font=ctk.CTkFont(size=26, weight="bold")
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text="High-definition microphone streaming from Android phone to Windows PC.",
            font=ctk.CTkFont(size=13),
            text_color="gray70"
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Status Banner Card
        self.status_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B", border_width=1, border_color="#2D3342")
        self.status_card.pack(fill="x", pady=(0, 15), ipady=6)

        status_inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_inner.pack(fill="x", padx=16, pady=8)

        self.status_dot = ctk.CTkLabel(
            status_inner,
            text="●",
            font=ctk.CTkFont(size=22),
            text_color="#FFA500"
        )
        self.status_dot.pack(side="left", padx=(0, 10))

        status_text_frame = ctk.CTkFrame(status_inner, fg_color="transparent")
        status_text_frame.pack(side="left", fill="x", expand=True)

        self.status_title = ctk.CTkLabel(
            status_text_frame,
            text="Waiting for Phone Connection...",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w"
        )
        self.status_title.pack(anchor="w")

        self.status_detail = ctk.CTkLabel(
            status_text_frame,
            text=f"Connect phone to {self.active_pc_ip}:{NetworkServer.AUDIO_PORT} or trigger below",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
            anchor="w"
        )
        self.status_detail.pack(anchor="w")

        # ------------------ Connection & IP Card ------------------
        conn_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B")
        conn_card.pack(fill="x", pady=(0, 15))

        conn_title = ctk.CTkLabel(
            conn_card,
            text="📡 PC Network Interface",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        conn_title.pack(anchor="w", padx=16, pady=(12, 6))

        # PC IP Selector Row
        ip_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        ip_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(ip_row, text="PC IP:", width=50, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        interface_labels = [item['label'] for item in self.interfaces]
        self.interface_combo = ctk.CTkOptionMenu(
            ip_row,
            values=interface_labels,
            width=360,
            height=32,
            command=self._on_interface_changed
        )
        self.interface_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.copy_ip_btn = ctk.CTkButton(
            ip_row,
            text="📋 Copy IP",
            width=85,
            height=32,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._copy_ip_to_clipboard
        )
        self.copy_ip_btn.pack(side="left")

        # ------------------ Phone IP Trigger Card ------------------
        phone_trigger_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        phone_trigger_row.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkLabel(phone_trigger_row, text="Phone IP:", width=70, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.phone_ip_entry = ctk.CTkEntry(
            phone_trigger_row,
            placeholder_text="Enter Phone Wi-Fi IP (e.g. 192.168.0.105)",
            height=32
        )
        self.phone_ip_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.trigger_btn = ctk.CTkButton(
            phone_trigger_row,
            text="🚀 Trigger Phone",
            width=125,
            height=32,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._trigger_phone_connection
        )
        self.trigger_btn.pack(side="left")

        # Quick Actions Row (USB & Firewall)
        quick_act_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        quick_act_row.pack(fill="x", padx=16, pady=(0, 12))

        self.usb_btn = ctk.CTkButton(
            quick_act_row,
            text="🔌 Connect via USB Cable (ADB)",
            height=30,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self._setup_usb_bridge
        )
        self.usb_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.firewall_btn = ctk.CTkButton(
            quick_act_row,
            text="🛡️ Allow in Windows Firewall",
            height=30,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._run_firewall_fix
        )
        self.firewall_btn.pack(side="left", expand=True, fill="x")

        # ------------------ Audio Device Selector Card ------------------
        audio_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B")
        audio_card.pack(fill="x", pady=(0, 15))

        audio_head = ctk.CTkFrame(audio_card, fg_color="transparent")
        audio_head.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(audio_head, text="🔊 Audio Routing Target", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        refresh_dev_btn = ctk.CTkButton(
            audio_head,
            text="🔄 Refresh",
            width=70,
            height=26,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._refresh_audio_devices
        )
        refresh_dev_btn.pack(side="right")

        # Audio Device Dropdown
        dev_frame = ctk.CTkFrame(audio_card, fg_color="transparent")
        dev_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.device_combo = ctk.CTkOptionMenu(
            dev_frame,
            values=["Scanning devices..."],
            height=36,
            command=self._on_device_selected
        )
        self.device_combo.pack(fill="x", pady=(0, 8))

        # VB-Audio Cable Banner
        self.vbcable_frame = ctk.CTkFrame(audio_card, fg_color="#2A2318", corner_radius=8, border_width=1, border_color="#784B12")
        self.vbcable_frame.pack(fill="x", padx=16, pady=(0, 12))

        vbcable_inner = ctk.CTkFrame(self.vbcable_frame, fg_color="transparent")
        vbcable_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            vbcable_inner,
            text="💡 To use in Discord, Zoom, Games or Windows Apps as a real Mic:\nSelect 'CABLE Input (VB-Audio Virtual Cable)'. Then pick 'CABLE Output' in Discord/Zoom.",
            font=ctk.CTkFont(size=12),
            text_color="#FBBF24",
            justify="left"
        ).pack(side="left", padx=(0, 15))

        vbcable_btn = ctk.CTkButton(
            vbcable_inner,
            text="Install VB-CABLE",
            width=120,
            height=30,
            fg_color="#D97706",
            hover_color="#B45309",
            command=lambda: webbrowser.open("https://vb-audio.com/Cable/")
        )
        vbcable_btn.pack(side="right")

        # ------------------ Live VU Meter Visualizer ------------------
        vu_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B")
        vu_card.pack(fill="x", pady=(0, 15))

        vu_head = ctk.CTkFrame(vu_card, fg_color="transparent")
        vu_head.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(vu_head, text="📊 Live Microphone Level", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.db_label = ctk.CTkLabel(vu_head, text="-∞ dB", font=ctk.CTkFont(size=13, weight="bold"), text_color="gray70")
        self.db_label.pack(side="right")

        # VU Canvas
        self.vu_canvas = ctk.CTkCanvas(vu_card, height=22, bg="#111318", highlightthickness=0)
        self.vu_canvas.pack(fill="x", padx=16, pady=(0, 8))

        # Decibel Tick Marks
        ticks_frame = ctk.CTkFrame(vu_card, fg_color="transparent")
        ticks_frame.pack(fill="x", padx=16, pady=(0, 12))
        for mark in ["-50dB", "-40dB", "-30dB", "-20dB", "-10dB", "-3dB", "0dB"]:
            ctk.CTkLabel(ticks_frame, text=mark, font=ctk.CTkFont(size=10), text_color="gray50").pack(side="left", expand=True)

        # ------------------ Controls & Tuning Card ------------------
        ctrl_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B")
        ctrl_card.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(ctrl_card, text="⚙️ Audio Tuning & Controls", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(12, 10))

        # Gain Slider Row
        gain_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        gain_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(gain_row, text="Mic Gain / Boost:", width=130, anchor="w", font=ctk.CTkFont(size=13)).pack(side="left")

        self.gain_slider = ctk.CTkSlider(
            gain_row,
            from_=0.1,
            to=3.0,
            number_of_steps=29,
            command=self._on_gain_changed
        )
        self.gain_slider.set(1.0)
        self.gain_slider.pack(side="left", fill="x", expand=True, padx=(10, 15))

        self.gain_val_lbl = ctk.CTkLabel(gain_row, text="100%", width=45, font=ctk.CTkFont(size=13, weight="bold"), text_color="#4CA3FF")
        self.gain_val_lbl.pack(side="left")

        # Buffer / Latency Selector Row
        buf_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        buf_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(buf_row, text="Latency Profile:", width=130, anchor="w", font=ctk.CTkFont(size=13)).pack(side="left")

        self.buffer_seg = ctk.CTkSegmentedButton(
            buf_row,
            values=["Ultra Low (~12ms)", "Balanced (~23ms)", "High Stability (~46ms)"],
            command=self._on_buffer_profile_changed
        )
        self.buffer_seg.set("Balanced (~23ms)")
        self.buffer_seg.pack(side="left", fill="x", expand=True)

        # Action Buttons Row (Mute, Monitor Self)
        act_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        act_row.pack(fill="x", padx=16, pady=(0, 14))

        self.mute_btn = ctk.CTkButton(
            act_row,
            text="🔇 Mute Mic",
            width=130,
            height=34,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._toggle_mute
        )
        self.mute_btn.pack(side="left", padx=(0, 12))

        self.monitor_btn = ctk.CTkButton(
            act_row,
            text="🎧 Listen to Myself (Off)",
            width=180,
            height=34,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._toggle_monitor_self
        )
        self.monitor_btn.pack(side="left")

        # ------------------ Activity Log Card ------------------
        log_card = ctk.CTkFrame(self.scroll_frame, corner_radius=12, fg_color="#1E222B")
        log_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(log_card, text="📝 Activity Log", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=16, pady=(10, 6))

        self.log_box = ctk.CTkTextbox(log_card, height=90, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#14171F")
        self.log_box.pack(fill="x", padx=16, pady=(0, 12))
        self.log_box.configure(state="disabled")

    def log(self, message: str):
        """Appends a timestamped log to the UI log console."""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", formatted)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _start_services(self):
        """Initializes devices, starts audio playback and network servers."""
        self._refresh_audio_devices()
        self.network_server.start()
        self.log(f"AirMic Server active on UDP/TCP port {NetworkServer.AUDIO_PORT}")
        self.log(f"Active PC IP: {self.active_pc_ip}")
        self.log(f"Auto-Discovery Beacon transmitting on port {NetworkServer.DISCOVERY_PORT}")

    def _on_interface_changed(self, choice):
        """User switched the network interface in dropdown."""
        for item in self.interfaces:
            if item['label'] == choice:
                self.active_pc_ip = item['ip']
                self.network_server.set_active_ip(self.active_pc_ip)
                self.status_detail.configure(
                    text=f"Connect phone to {self.active_pc_ip}:{NetworkServer.AUDIO_PORT} or trigger below"
                )
                self.log(f"Switched active PC IP to: {self.active_pc_ip}")
                break

    def _trigger_phone_connection(self):
        """Sends a connection probe/trigger to the specified phone IP."""
        phone_ip = self.phone_ip_entry.get().strip()
        if not phone_ip:
            self.log("⚠️ Please enter a Phone IP address to trigger.")
            return

        self.log(f"Sending connection trigger to Phone at {phone_ip}...")
        ok, msg = self.network_server.send_connect_request_to_phone(phone_ip)
        self.log(msg)
        if ok:
            self.trigger_btn.configure(text="Trigger Sent!", fg_color="#059669")
            self.after(2000, lambda: self.trigger_btn.configure(text="🚀 Trigger Phone", fg_color="#10B981"))

    def _refresh_audio_devices(self):
        """Queries and lists Windows audio output devices."""
        self.devices = AudioEngine.get_output_devices()
        if not self.devices:
            self.device_combo.configure(values=["No output devices found"])
            return

        display_names = []
        preferred_idx = 0

        for i, dev in enumerate(self.devices):
            prefix = "⭐ [VIRTUAL MIC] " if dev['is_vb_cable'] else ""
            default_tag = " (Default)" if dev['is_default'] else ""
            item_label = f"{prefix}{dev['display_name']}{default_tag}"
            display_names.append(item_label)

            if dev['is_vb_cable']:
                preferred_idx = i
            elif dev['is_default'] and not any(d['is_vb_cable'] for d in self.devices[:i]):
                preferred_idx = i

        self.device_combo.configure(values=display_names)
        self.device_combo.set(display_names[preferred_idx])
        self._select_device_by_index(preferred_idx)

    def _on_device_selected(self, choice_str):
        values = self.device_combo.cget("values")
        if choice_str in values:
            idx = values.index(choice_str)
            self._select_device_by_index(idx)

    def _select_device_by_index(self, list_idx):
        if 0 <= list_idx < len(self.devices):
            target_dev = self.devices[list_idx]
            self.selected_device_idx = target_dev['index']
            ok, msg = self.audio_engine.start(self.selected_device_idx)
            if ok:
                self.log(f"Audio output routed to: {target_dev['name']}")
            else:
                self.log(f"Audio device error: {msg}")

    def _on_gain_changed(self, val):
        pct = int(val * 100)
        self.gain_val_lbl.configure(text=f"{pct}%")
        self.audio_engine.set_gain(val)

    def _on_buffer_profile_changed(self, profile):
        if "Ultra Low" in profile:
            self.audio_engine.set_buffer_size(256)
            self.log("Latency profile set to Ultra Low (~12ms)")
        elif "Balanced" in profile:
            self.audio_engine.set_buffer_size(512)
            self.log("Latency profile set to Balanced (~23ms)")
        else:
            self.audio_engine.set_buffer_size(1024)
            self.log("Latency profile set to High Stability (~46ms)")
        
        if self.selected_device_idx is not None:
            self.audio_engine.start(self.selected_device_idx)

    def _toggle_mute(self):
        new_state = not self.audio_engine.is_muted
        self.audio_engine.set_mute(new_state)
        if new_state:
            self.mute_btn.configure(text="🔊 Unmute Mic", fg_color="#DC2626", hover_color="#B91C1C")
            self.log("Microphone Muted")
        else:
            self.mute_btn.configure(text="🔇 Mute Mic", fg_color="#374151", hover_color="#4B5563")
            self.log("Microphone Unmuted")

    def _toggle_monitor_self(self):
        self.is_monitoring_self = not self.is_monitoring_self
        if self.is_monitoring_self:
            default_devs = [d for d in self.devices if d['is_default']]
            if default_devs:
                self.audio_engine.start(default_devs[0]['index'])
                self.monitor_btn.configure(text="🎧 Listen to Myself (ON)", fg_color="#10B981", hover_color="#059669")
                self.log(f"Self-Monitoring ENABLED via {default_devs[0]['name']}")
        else:
            if self.selected_device_idx is not None:
                self.audio_engine.start(self.selected_device_idx)
            self.monitor_btn.configure(text="🎧 Listen to Myself (Off)", fg_color="#374151", hover_color="#4B5563")
            self.log("Self-Monitoring DISABLED (Routed back to target device)")

    def _copy_ip_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.active_pc_ip)
        self.copy_ip_btn.configure(text="Copied!")
        self.after(1500, lambda: self.copy_ip_btn.configure(text="📋 Copy IP"))

    def _setup_usb_bridge(self):
        self.log("Scanning for USB-connected Android phone...")
        threading.Thread(target=self._async_usb_setup, daemon=True).start()

    def _async_usb_setup(self):
        ok, msg = USBBridge.forward_ports(NetworkServer.AUDIO_PORT)
        self.after(0, lambda: self.log(msg))
        if ok:
            self.after(0, lambda: self.usb_btn.configure(text="✅ USB Active", fg_color="#059669"))
            self.after(3000, lambda: self.usb_btn.configure(text="🔌 Connect via USB Cable (ADB)", fg_color="#2563EB"))

    def _run_firewall_fix(self):
        """Runs the Windows firewall helper."""
        self.log("Opening Windows Firewall configurator...")
        try:
            bat_path = os.path.join(os.path.dirname(__file__), "..", "Fix_Firewall.bat")
            if os.path.exists(bat_path):
                subprocess.Popen(["cmd.exe", "/c", bat_path])
            else:
                self.log("Fix_Firewall.bat not found.")
        except Exception as e:
            self.log(f"Firewall config error: {e}")

    def on_network_status_change(self, connected: bool, client_ip: str, message: str):
        self.after(0, lambda: self._apply_network_status(connected, client_ip, message))

    def _apply_network_status(self, connected: bool, client_ip: str, message: str):
        self.log(message)
        if connected:
            # Auto-fill detected phone IP in entry if empty
            if client_ip and not self.phone_ip_entry.get().strip():
                self.phone_ip_entry.delete(0, "end")
                self.phone_ip_entry.insert(0, client_ip)

            self.status_dot.configure(text_color="#10B981")  # Green
            self.status_title.configure(text=f"Phone Connected: {client_ip}")
            self.status_detail.configure(text=f"Streaming live audio • {self.network_server.kbps:.1f} kbps")
            self.status_card.configure(border_color="#10B981")
        else:
            self.status_dot.configure(text_color="#FFA500")  # Orange/Yellow
            self.status_title.configure(text="Waiting for Phone Connection...")
            self.status_detail.configure(text=f"Connect phone to {self.active_pc_ip}:{NetworkServer.AUDIO_PORT} or trigger above")
            self.status_card.configure(border_color="#2D3342")

    def _ui_update_loop(self):
        level = self.audio_engine.current_level
        db = self.audio_engine.current_rms_db
        
        canvas_width = self.vu_canvas.winfo_width()
        canvas_height = self.vu_canvas.winfo_height()

        self.vu_canvas.delete("all")
        if canvas_width > 10 and level > 0.01:
            bar_width = int(canvas_width * level)
            
            if level < 0.6:
                color = "#10B981"  # Emerald green
            elif level < 0.85:
                color = "#F59E0B"  # Amber/Yellow
            else:
                color = "#EF4444"  # Red

            self.vu_canvas.create_rectangle(
                0, 0, bar_width, canvas_height,
                fill=color, width=0
            )

        if db > -80:
            self.db_label.configure(text=f"{db:.1f} dB")
        else:
            self.db_label.configure(text="-∞ dB")

        if self.network_server.client_ip:
            self.status_detail.configure(
                text=f"Streaming from {self.network_server.client_ip} • {self.network_server.kbps:.1f} kbps • {self.audio_engine.sample_rate}Hz 16-bit PCM"
            )

        self.after(33, self._ui_update_loop)

    def on_closing(self):
        self.audio_engine.stop()
        self.network_server.stop()
        self.destroy()


def main():
    app = AirMicApp()
    app.mainloop()


if __name__ == "__main__":
    main()
