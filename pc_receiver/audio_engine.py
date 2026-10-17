"""
AirMic PC Audio Engine
Handles real-time audio playback, device routing, gain control, 
VU-meter level calculation, and low-latency buffering.
"""

import math
import numpy as np
import queue
import sounddevice as sd
import threading
import time


class AudioEngine:
    DEFAULT_SAMPLE_RATE = 44100
    CHANNELS = 2  # Stereo output (mono duplicated) for 100% Windows device compatibility

    def __init__(self, sample_rate=DEFAULT_SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.device_index = None
        self.stream = None
        self.audio_queue = queue.Queue(maxsize=60)
        self.gain = 1.0
        self.is_muted = False
        self.is_running = False
        self.current_rms_db = -90.0
        self.current_level = 0.0  # 0.0 to 1.0 normalized
        self.underrun_count = 0
        self.lock = threading.Lock()
        self.buffer_size = 512  # ~11.6ms chunks for ultra low latency

    @staticmethod
    def get_output_devices():
        """Returns a list of all output-capable devices on Windows."""
        devices = []
        try:
            device_list = sd.query_devices()
            default_out = sd.default.device[1]

            for idx, dev in enumerate(device_list):
                if dev['max_output_channels'] > 0:
                    name = dev['name']
                    host_api_name = sd.query_hostapis(dev['hostapi'])['name']
                    is_default = (idx == default_out)
                    is_vb_cable = "cable input" in name.lower() or "vb-audio" in name.lower()
                    
                    devices.append({
                        'index': idx,
                        'name': name,
                        'host_api': host_api_name,
                        'display_name': f"{name} ({host_api_name})",
                        'is_default': is_default,
                        'is_vb_cable': is_vb_cable,
                        'max_channels': dev['max_output_channels']
                    })
        except Exception as e:
            print(f"[AudioEngine] Error querying devices: {e}")
        return devices

    def set_gain(self, gain_multiplier: float):
        """Sets the audio gain (0.0 to 3.0)."""
        self.gain = max(0.0, min(float(gain_multiplier), 4.0))

    def set_mute(self, muted: bool):
        """Mutes or unmutes the audio output."""
        self.is_muted = bool(muted)

    def set_buffer_size(self, size: int):
        """Sets the callback buffer size (256, 512, 1024)."""
        self.buffer_size = size

    def push_pcm_data(self, raw_bytes: bytes):
        """
        Receives raw 16-bit PCM bytes (mono) from network and enqueues.
        """
        if not self.is_running or self.is_muted:
            if self.is_muted:
                self.current_level = 0.0
                self.current_rms_db = -90.0
            return

        try:
            # Convert raw 16-bit signed PCM to float32 (-1.0 to 1.0)
            audio_array = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Calculate RMS for visual VU meter
            if len(audio_array) > 0:
                rms = np.sqrt(np.mean(audio_array ** 2))
                if rms > 1e-5:
                    db = 20.0 * math.log10(rms)
                    self.current_rms_db = max(-60.0, min(0.0, db))
                    # Normalized level: -50 dB to 0 dB mapped to 0.0 - 1.0
                    self.current_level = max(0.0, min(1.0, (self.current_rms_db + 50.0) / 50.0))
                else:
                    self.current_rms_db = -90.0
                    self.current_level = 0.0

            # Apply Gain with soft-clipping limiter (np.tanh)
            if self.gain != 1.0:
                audio_array = np.tanh(audio_array * self.gain)

            # Duplicate mono to stereo for universal Windows audio endpoint compatibility
            stereo_data = np.column_stack((audio_array, audio_array))

            # Put into playback queue, drop oldest if queue full to maintain real-time latency
            try:
                self.audio_queue.put_nowait(stereo_data)
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
                self.audio_queue.put_nowait(stereo_data)
                self.underrun_count += 1
        except Exception as e:
            pass

    def _audio_callback(self, outdata, frames, time_info, status):
        """PortAudio output stream callback."""
        if status.output_underflow:
            self.underrun_count += 1

        chunk_list = []
        needed = frames
        while needed > 0:
            try:
                data = self.audio_queue.get_nowait()
                if len(data) <= needed:
                    chunk_list.append(data)
                    needed -= len(data)
                else:
                    # Partial chunk needed
                    chunk_list.append(data[:needed])
                    # Re-enqueue remaining
                    self.audio_queue.put(data[needed:])
                    needed = 0
            except queue.Empty:
                break

        if chunk_list:
            filled = np.vstack(chunk_list)
            outdata[:len(filled)] = filled
            if len(filled) < frames:
                outdata[len(filled):] = 0.0  # Silence padding
        else:
            outdata.fill(0.0)
            self.current_level = max(0.0, self.current_level * 0.85)

    def start(self, device_index=None):
        """Starts the audio output stream."""
        with self.lock:
            if self.is_running:
                self.stop()

            self.device_index = device_index
            self.is_running = True
            
            # Clear previous queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break

            try:
                self.stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=self.CHANNELS,
                    dtype='float32',
                    device=self.device_index,
                    blocksize=self.buffer_size,
                    callback=self._audio_callback
                )
                self.stream.start()
                return True, "Audio stream started successfully"
            except Exception as e:
                self.is_running = False
                return False, f"Failed to start audio stream: {e}"

    def stop(self):
        """Stops the audio output stream."""
        with self.lock:
            self.is_running = False
            self.current_level = 0.0
            self.current_rms_db = -90.0
            if self.stream:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
