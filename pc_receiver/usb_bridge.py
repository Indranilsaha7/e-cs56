"""
AirMic USB Bridge Helper
Manages ADB (Android Debug Bridge) port forwarding for wired zero-latency mic streaming.
"""

import os
import shutil
import subprocess


class USBBridge:
    @staticmethod
    def find_adb_path():
        """Locates adb.exe either in PATH or in the standard Android SDK folder."""
        # 1. Check system PATH
        adb = shutil.which("adb")
        if adb and os.path.isfile(adb):
            return adb

        # 2. Check LOCALAPPDATA Android SDK
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
            if os.path.isfile(candidate):
                return candidate

        # 3. Check Program Files
        candidate = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Android", "platform-tools", "adb.exe")
        if os.path.isfile(candidate):
            return candidate

        return None

    @classmethod
    def list_connected_devices(cls):
        """Returns list of connected Android device serials."""
        adb_path = cls.find_adb_path()
        if not adb_path:
            return []

        try:
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            devices = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
            return devices
        except Exception:
            return []

    @classmethod
    def forward_ports(cls, port=55555):
        """
        Runs adb forward and adb reverse for both TCP and UDP port connections.
        """
        adb_path = cls.find_adb_path()
        if not adb_path:
            return False, "ADB was not found. Please enable USB Debugging or install Android SDK."

        devices = cls.list_connected_devices()
        if not devices:
            return False, "No Android device detected via USB. Make sure USB Debugging is turned ON in Developer Options."

        try:
            # Forward TCP port so localhost:55555 routes to phone
            subprocess.run(
                [adb_path, "forward", f"tcp:{port}", f"tcp:{port}"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            # Reverse TCP port so phone connecting to localhost:55555 routes to PC
            subprocess.run(
                [adb_path, "reverse", f"tcp:{port}", f"tcp:{port}"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return True, f"USB Bridge established! Device: {devices[0]}. Use 127.0.0.1 on the phone."
        except Exception as e:
            return False, f"Error configuring ADB: {e}"
