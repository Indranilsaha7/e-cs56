package com.airmic.app

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.log10
import kotlin.math.sqrt

class AudioStreamer(
    private val host: String,
    private val port: Int,
    private val isUdp: Boolean = true,
    private val enableNoiseSuppressor: Boolean = true,
    private val onLevelUpdate: ((rmsDb: Float, normalized: Float) -> Unit)? = null,
    private val onError: ((String) -> Unit)? = null
) {
    companion object {
        const val SAMPLE_RATE = 44100
        const val CHUNK_SAMPLES = 1024 // 1024 samples @ 44.1kHz = ~23.2ms
    }

    @Volatile
    private var isStreaming = false
    @Volatile
    var gain: Float = 1.0f
    @Volatile
    var isMuted: Boolean = false

    private var audioRecord: AudioRecord? = null
    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null

    private var udpSocket: DatagramSocket? = null
    private var tcpSocket: Socket? = null
    private var tcpOutputStream: OutputStream? = null

    @SuppressLint("MissingPermission")
    suspend fun start() = withContext(Dispatchers.IO) {
        val minBufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        val bufferSize = maxOf(minBufferSize, CHUNK_SAMPLES * 2 * 4)

        // Try VOICE_COMMUNICATION first for hardware noise cancellation, fallback to MIC
        var record: AudioRecord? = null
        val sources = arrayOf(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            MediaRecorder.AudioSource.MIC
        )

        for (source in sources) {
            try {
                val candidate = AudioRecord(
                    source,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize
                )
                if (candidate.state == AudioRecord.STATE_INITIALIZED) {
                    record = candidate
                    break
                } else {
                    candidate.release()
                }
            } catch (e: Exception) {
                // Try next source
            }
        }

        if (record == null) {
            onError?.invoke("Failed to initialize AudioRecord. Please check microphone permissions.")
            return@withContext
        }
        audioRecord = record

        // Attach hardware effects if supported
        val audioSessionId = record.audioSessionId
        if (enableNoiseSuppressor && NoiseSuppressor.isAvailable()) {
            try {
                noiseSuppressor = NoiseSuppressor.create(audioSessionId).apply {
                    enabled = true
                }
            } catch (e: Exception) {
                // Effect not supported
            }
        }
        if (AcousticEchoCanceler.isAvailable()) {
            try {
                echoCanceler = AcousticEchoCanceler.create(audioSessionId).apply {
                    enabled = true
                }
            } catch (e: Exception) {
                // Effect not supported
            }
        }

        // Initialize Network connection
        try {
            val address = InetAddress.getByName(host)
            if (isUdp) {
                udpSocket = DatagramSocket()
            } else {
                val s = Socket(address, port)
                s.tcpNoDelay = true
                s.sendBufferSize = 65536
                tcpSocket = s
                tcpOutputStream = s.getOutputStream()
            }
        } catch (e: Exception) {
            onError?.invoke("Network error connecting to $host:$port - ${e.message}")
            stop()
            return@withContext
        }

        val shortBuffer = ShortArray(CHUNK_SAMPLES)
        val byteBuffer = ByteBuffer.allocate(CHUNK_SAMPLES * 2).order(ByteOrder.LITTLE_ENDIAN)
        val targetAddress = InetAddress.getByName(host)
        val datagramPacket = DatagramPacket(byteBuffer.array(), byteBuffer.capacity(), targetAddress, port)

        try {
            record.startRecording()
            isStreaming = true

            while (isStreaming) {
                val readShorts = record.read(shortBuffer, 0, CHUNK_SAMPLES)
                if (readShorts <= 0) continue

                // Compute RMS and Decibels for VU meter
                var sumSquares = 0.0
                for (i in 0 until readShorts) {
                    val s = shortBuffer[i].toDouble()
                    sumSquares += s * s
                }
                val rms = sqrt(sumSquares / readShorts)
                val rmsRatio = (rms / 32768.0).coerceIn(1e-5, 1.0)
                val db = (20.0 * log10(rmsRatio)).toFloat()
                // Map -60dB -> 0.0, 0dB -> 1.0
                val normalized = ((db + 60.0f) / 60.0f).coerceIn(0.0f, 1.0f)
                onLevelUpdate?.invoke(db, if (isMuted) 0f else normalized)

                // Apply Software Gain and Mute
                byteBuffer.clear()
                val currentGain = gain
                val muted = isMuted

                for (i in 0 until readShorts) {
                    if (muted) {
                        byteBuffer.putShort(0)
                    } else {
                        var sample = (shortBuffer[i] * currentGain).toInt()
                        sample = sample.coerceIn(-32768, 32767)
                        byteBuffer.putShort(sample.toShort())
                    }
                }

                val payload = byteBuffer.array()

                // Transmit audio chunk
                if (isUdp) {
                    datagramPacket.setData(payload, 0, readShorts * 2)
                    udpSocket?.send(datagramPacket)
                } else {
                    tcpOutputStream?.write(payload, 0, readShorts * 2)
                }
            }
        } catch (e: Exception) {
            if (isStreaming) {
                onError?.invoke("Streaming stopped: ${e.message}")
            }
        } finally {
            stop()
        }
    }

    fun stop() {
        isStreaming = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            // Ignored
        }
        audioRecord = null

        try {
            noiseSuppressor?.release()
            echoCanceler?.release()
        } catch (e: Exception) {
            // Ignored
        }
        noiseSuppressor = null
        echoCanceler = null

        try {
            udpSocket?.close()
        } catch (e: Exception) {
            // Ignored
        }
        udpSocket = null

        try {
            tcpOutputStream?.close()
            tcpSocket?.close()
        } catch (e: Exception) {
            // Ignored
        }
        tcpOutputStream = null
        tcpSocket = null
    }
}
