package com.airmic.app

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
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
        const val CHUNK_SAMPLES = 960 // 960 samples @ 48kHz = 20ms audio frame
        val SAMPLE_RATES = intArrayOf(48000, 44100, 16000)
    }

    @Volatile
    private var isStreaming = false
    @Volatile
    var gain: Float = 1.0f
    @Volatile
    var isMuted: Boolean = false

    private var audioRecord: AudioRecord? = null
    private var activeSampleRate = 48000

    private var udpSocket: DatagramSocket? = null
    private var tcpSocket: Socket? = null
    private var tcpOutputStream: OutputStream? = null

    @SuppressLint("MissingPermission")
    suspend fun start() = withContext(Dispatchers.IO) {
        var record: AudioRecord? = null
        var chosenRate = 48000

        // Prioritize standard MIC and CAMCORDER (clean uncompressed capture)
        val sources = intArrayOf(
            MediaRecorder.AudioSource.MIC,
            MediaRecorder.AudioSource.DEFAULT,
            MediaRecorder.AudioSource.CAMCORDER,
            MediaRecorder.AudioSource.VOICE_RECOGNITION
        )

        outer@ for (rate in SAMPLE_RATES) {
            val minBuf = AudioRecord.getMinBufferSize(
                rate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )
            if (minBuf <= 0) continue

            val bufSize = maxOf(minBuf * 2, CHUNK_SAMPLES * 2 * 4)

            for (src in sources) {
                try {
                    val candidate = AudioRecord(
                        src,
                        rate,
                        AudioFormat.CHANNEL_IN_MONO,
                        AudioFormat.ENCODING_PCM_16BIT,
                        bufSize
                    )
                    if (candidate.state == AudioRecord.STATE_INITIALIZED) {
                        record = candidate
                        chosenRate = rate
                        break@outer
                    } else {
                        candidate.release()
                    }
                } catch (e: Exception) {
                    // Try next
                }
            }
        }

        if (record == null) {
            onError?.invoke("Microphone initialization failed. Please check app audio permissions.")
            return@withContext
        }

        audioRecord = record
        activeSampleRate = chosenRate

        // Connect Network
        try {
            val address = InetAddress.getByName(host)
            if (isUdp) {
                udpSocket = DatagramSocket()
                udpSocket?.sendBufferSize = 65536
            } else {
                val s = Socket(address, port)
                s.tcpNoDelay = true
                s.sendBufferSize = 65536
                tcpSocket = s
                tcpOutputStream = s.getOutputStream()
            }
        } catch (e: Exception) {
            onError?.invoke("Network error connecting to $host:$port: ${e.message}")
            stop()
            return@withContext
        }

        val shortBuffer = ShortArray(CHUNK_SAMPLES)
        // 8 bytes header + PCM data:
        // [0..3]: 'AMIC'
        // [4..5]: sample_rate (u16 LE)
        // [6]: channels (1)
        // [7]: flags (0)
        val headerSize = 8
        val byteBuffer = ByteBuffer.allocate(headerSize + CHUNK_SAMPLES * 2).order(ByteOrder.LITTLE_ENDIAN)
        val targetAddress = InetAddress.getByName(host)
        val datagramPacket = DatagramPacket(byteBuffer.array(), byteBuffer.capacity(), targetAddress, port)

        try {
            record.startRecording()
            isStreaming = true

            while (isStreaming) {
                val readShorts = record.read(shortBuffer, 0, CHUNK_SAMPLES)
                if (readShorts <= 0) {
                    Thread.sleep(5)
                    continue
                }

                // Compute RMS & dB for VU meter
                var sumSquares = 0.0
                for (i in 0 until readShorts) {
                    val s = shortBuffer[i].toDouble()
                    sumSquares += s * s
                }
                val rms = sqrt(sumSquares / readShorts)
                val rmsRatio = (rms / 32768.0).coerceIn(1e-5, 1.0)
                val db = (20.0 * log10(rmsRatio)).toFloat()
                val normalized = ((db + 50.0f) / 50.0f).coerceIn(0.0f, 1.0f)
                onLevelUpdate?.invoke(db, if (isMuted) 0f else normalized)

                // Fill Header
                byteBuffer.clear()
                byteBuffer.put('A'.code.toByte())
                byteBuffer.put('M'.code.toByte())
                byteBuffer.put('I'.code.toByte())
                byteBuffer.put('C'.code.toByte())
                byteBuffer.putShort(activeSampleRate.toShort())
                byteBuffer.put(1.toByte()) // 1 channel (mono)
                byteBuffer.put(0.toByte()) // flags

                // Fill Audio Samples with Gain / Mute
                val currentGain = gain
                val muted = isMuted

                for (i in 0 until readShorts) {
                    if (muted) {
                        byteBuffer.putShort(0)
                    } else if (currentGain == 1.0f) {
                        byteBuffer.putShort(shortBuffer[i])
                    } else {
                        var sample = (shortBuffer[i] * currentGain).toInt()
                        sample = sample.coerceIn(-32768, 32767)
                        byteBuffer.putShort(sample.toShort())
                    }
                }

                val payloadLen = headerSize + readShorts * 2
                val payload = byteBuffer.array()

                if (isUdp) {
                    datagramPacket.setData(payload, 0, payloadLen)
                    udpSocket?.send(datagramPacket)
                } else {
                    tcpOutputStream?.write(payload, 0, payloadLen)
                }
            }
        } catch (e: Exception) {
            if (isStreaming) {
                onError?.invoke("Streaming interrupted: ${e.message}")
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
