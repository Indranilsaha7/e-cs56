"""
AirMic Network Server
Handles UDP & TCP audio stream reception from the Android app,
along with UDP LAN Auto-Discovery and Phone-IP triggering.
"""

import json
import socket
import threading
import time


class NetworkServer:
    AUDIO_PORT = 55555
    DISCOVERY_PORT = 55554
    PACKET_SIZE = 4096

    def __init__(self, on_audio_chunk=None, on_status_change=None):
        self.on_audio_chunk = on_audio_chunk
        self.on_status_change = on_status_change
        
        self.is_running = False
        self.udp_socket = None
        self.tcp_socket = None
        self.discovery_socket = None
        
        self.selected_pc_ip = None
        self.client_ip = None
        self.client_port = None
        self.last_packet_time = 0.0
        self.total_bytes_received = 0
        self.packets_per_sec = 0
        self.kbps = 0.0
        
        self._thread_udp = None
        self._thread_tcp = None
        self._thread_discovery = None
        self._thread_monitor = None
        self._lock = threading.Lock()

    @staticmethod
    def get_lan_interfaces():
        """
        Returns a sorted list of local IPv4 network addresses with adapter hints.
        Prioritizes standard Wi-Fi/LAN subnets (192.168.x.x, 10.x.x.x) over
        virtual adapters (Hyper-V / Docker 172.16-31.x.x, WSL, etc.).
        """
        interfaces = []
        seen_ips = set()

        # Method 1: Find default gateway interface by route probing
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                primary_ip = s.getsockname()[0]
                if primary_ip not in seen_ips and not primary_ip.startswith("127."):
                    seen_ips.add(primary_ip)
                    interfaces.append({
                        'ip': primary_ip,
                        'is_primary': True,
                        'label': f"{primary_ip} (Default Gateway / Active Wi-Fi)"
                    })
            finally:
                s.close()
        except Exception:
            pass

        # Method 2: Enumerate all IPs from hostname
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip in seen_ips or ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                seen_ips.add(ip)

                # Classify adapter
                if ip.startswith("192.168."):
                    label = f"{ip} (Local Wi-Fi / LAN)"
                elif ip.startswith("10."):
                    label = f"{ip} (Private LAN)"
                elif ip.startswith("172."):
                    # Hyper-V / Docker default switch often 172.16-31.x.x
                    parts = ip.split(".")
                    if len(parts) == 4 and 16 <= int(parts[1]) <= 31:
                        label = f"{ip} (Virtual Switch / Hyper-V / WSL)"
                    else:
                        label = f"{ip} (Network Interface)"
                else:
                    label = f"{ip} (Network Interface)"

                interfaces.append({
                    'ip': ip,
                    'is_primary': False,
                    'label': label
                })
        except Exception:
            pass

        if not interfaces:
            interfaces.append({
                'ip': '127.0.0.1',
                'is_primary': True,
                'label': '127.0.0.1 (Localhost / USB)'
            })

        # Sort: Primary first, then 192.168.x.x, then 10.x.x.x, then others, Virtual switches last
        def sort_key(item):
            ip = item['ip']
            if item.get('is_primary'):
                return 0
            if ip.startswith("192.168."):
                return 1
            if ip.startswith("10."):
                return 2
            if ip.startswith("172.") and "Virtual Switch" in item['label']:
                return 9
            return 3

        interfaces.sort(key=sort_key)
        return interfaces

    @classmethod
    def get_lan_ips(cls):
        """Returns just the list of IP strings, best first."""
        return [item['ip'] for item in cls.get_lan_interfaces()]

    @staticmethod
    def get_subnet_broadcast(ip: str) -> str:
        """Calculates subnet broadcast address assuming /24 for 192.168.x.x."""
        try:
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
        except Exception:
            pass
        return "255.255.255.255"

    def set_active_ip(self, ip: str):
        """Sets the designated PC IP address to advertise to the phone."""
        self.selected_pc_ip = ip

    def send_connect_request_to_phone(self, phone_ip: str, port=55554):
        """
        Sends a remote-connect request directly to the phone's IP address.
        Tells the phone to start streaming audio to this PC.
        """
        try:
            target_pc_ip = self.selected_pc_ip or (self.get_lan_ips()[0] if self.get_lan_ips() else "127.0.0.1")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            
            payload = json.dumps({
                "protocol": "AIRMIC",
                "type": "CONNECT_REQUEST",
                "pc_ip": target_pc_ip,
                "port": self.AUDIO_PORT,
                "pc_name": socket.gethostname()
            }).encode('utf-8')

            sock.sendto(payload, (phone_ip, port))
            sock.close()
            return True, f"Sent connection trigger to phone at {phone_ip}:{port}"
        except Exception as e:
            return False, f"Failed to send connection request to {phone_ip}: {e}"

    def start(self, port=AUDIO_PORT):
        """Starts UDP, TCP, and Auto-Discovery listeners."""
        self.AUDIO_PORT = port
        self.is_running = True
        
        # 1. Start UDP Audio Receiver
        self._thread_udp = threading.Thread(target=self._run_udp_server, daemon=True, name="AirMic-UDP")
        self._thread_udp.start()

        # 2. Start TCP Audio Receiver
        self._thread_tcp = threading.Thread(target=self._run_tcp_server, daemon=True, name="AirMic-TCP")
        self._thread_tcp.start()

        # 3. Start Auto-Discovery Beacon & Responder
        self._thread_discovery = threading.Thread(target=self._run_discovery_service, daemon=True, name="AirMic-Discovery")
        self._thread_discovery.start()

        # 4. Start Client Connection Monitor (detects timeout/disconnect)
        self._thread_monitor = threading.Thread(target=self._run_client_monitor, daemon=True, name="AirMic-Monitor")
        self._thread_monitor.start()

    def stop(self):
        """Stops all servers and closes sockets."""
        self.is_running = False
        
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass

        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass

        if self.discovery_socket:
            try:
                self.discovery_socket.close()
            except Exception:
                pass

        if self.on_status_change:
            self.on_status_change(connected=False, client_ip=None, message="Server stopped")

    def _run_udp_server(self):
        """Listens for UDP packets containing raw PCM audio."""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Increase socket buffer to avoid kernel packet drops
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            self.udp_socket.bind(('0.0.0.0', self.AUDIO_PORT))
            self.udp_socket.settimeout(1.0)
        except Exception as e:
            if self.on_status_change:
                self.on_status_change(connected=False, client_ip=None, message=f"UDP Bind error: {e}")
            return

        while self.is_running:
            try:
                data, addr = self.udp_socket.recvfrom(self.PACKET_SIZE)
                if not data:
                    continue

                now = time.time()
                was_disconnected = (self.client_ip is None)
                self.client_ip = addr[0]
                self.client_port = addr[1]
                self.last_packet_time = now
                self.total_bytes_received += len(data)

                if was_disconnected and self.on_status_change:
                    self.on_status_change(connected=True, client_ip=self.client_ip, message=f"Phone connected: {self.client_ip} (UDP)")

                # Check for 8-byte AMIC header
                pcm_data = data
                if len(data) > 8 and data[:4] == b"AMIC":
                    pcm_data = data[8:]

                # Forward raw PCM chunk to AudioEngine
                if self.on_audio_chunk:
                    self.on_audio_chunk(pcm_data)

            except socket.timeout:
                continue
            except Exception as e:
                if not self.is_running:
                    break

    def _run_tcp_server(self):
        """Listens for TCP audio connections (fallback / tethering mode)."""
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('0.0.0.0', self.AUDIO_PORT))
            self.tcp_socket.listen(1)
            self.tcp_socket.settimeout(1.0)
        except Exception as e:
            pass

        while self.is_running and self.tcp_socket:
            try:
                conn, addr = self.tcp_socket.accept()
                conn.settimeout(2.0)
                self.client_ip = addr[0]
                self.client_port = addr[1]
                if self.on_status_change:
                    self.on_status_change(connected=True, client_ip=self.client_ip, message=f"Phone connected: {self.client_ip} (TCP)")

                while self.is_running:
                    try:
                        chunk = conn.recv(2048)
                        if not chunk:
                            break
                        self.last_packet_time = time.time()
                        self.total_bytes_received += len(chunk)
                        pcm_chunk = chunk
                        if len(chunk) > 8 and chunk[:4] == b"AMIC":
                            pcm_chunk = chunk[8:]
                        if self.on_audio_chunk:
                            self.on_audio_chunk(pcm_chunk)
                    except socket.timeout:
                        continue
                    except Exception:
                        break
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                if not self.is_running:
                    break

    def _run_discovery_service(self):
        """Responds to discovery broadcast pings from the phone and emits beacons."""
        try:
            self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.discovery_socket.bind(('0.0.0.0', self.DISCOVERY_PORT))
            self.discovery_socket.settimeout(1.0)
        except Exception:
            return

        last_beacon_broadcast = 0.0

        while self.is_running:
            now = time.time()
            chosen_ip = self.selected_pc_ip or (self.get_lan_ips()[0] if self.get_lan_ips() else "127.0.0.1")

            # 1. Listen for discover requests from phone
            try:
                data, addr = self.discovery_socket.recvfrom(1024)
                text = data.decode('utf-8', errors='ignore').strip()
                if "AIRMIC_DISCOVER" in text:
                    reply = json.dumps({
                        "protocol": "AIRMIC",
                        "type": "BEACON",
                        "ip": chosen_ip,
                        "audio_port": self.AUDIO_PORT,
                        "pc_name": socket.gethostname()
                    })
                    self.discovery_socket.sendto(reply.encode('utf-8'), addr)
            except socket.timeout:
                pass
            except Exception:
                if not self.is_running:
                    break

            # 2. Periodically broadcast beacon every 2 seconds
            if now - last_beacon_broadcast > 2.0:
                last_beacon_broadcast = now
                try:
                    beacon = json.dumps({
                        "protocol": "AIRMIC",
                        "type": "BEACON",
                        "ip": chosen_ip,
                        "audio_port": self.AUDIO_PORT,
                        "pc_name": socket.gethostname()
                    }).encode('utf-8')

                    # Broadcast to universal broadcast AND specific subnet broadcast
                    self.discovery_socket.sendto(beacon, ('255.255.255.255', self.DISCOVERY_PORT))
                    subnet_bcast = self.get_subnet_broadcast(chosen_ip)
                    if subnet_bcast != '255.255.255.255':
                        self.discovery_socket.sendto(beacon, (subnet_bcast, self.DISCOVERY_PORT))
                except Exception:
                    pass

    def _run_client_monitor(self):
        """Tracks client heartbeat and throughput."""
        prev_bytes = 0
        last_calc_time = time.time()

        while self.is_running:
            time.sleep(0.5)
            now = time.time()
            elapsed = now - last_calc_time

            if elapsed >= 1.0:
                bytes_diff = self.total_bytes_received - prev_bytes
                self.kbps = (bytes_diff * 8.0) / (elapsed * 1000.0)
                prev_bytes = self.total_bytes_received
                last_calc_time = now

            # Check timeout (if no packets for > 2.5s)
            if self.client_ip and (now - self.last_packet_time > 2.5):
                old_ip = self.client_ip
                self.client_ip = None
                self.client_port = None
                self.kbps = 0.0
                if self.on_status_change:
                    self.on_status_change(connected=False, client_ip=None, message=f"Disconnected from {old_ip} (Signal lost)")
