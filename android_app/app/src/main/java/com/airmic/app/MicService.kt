package com.airmic.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class MicService : Service() {

    companion object {
        const val CHANNEL_ID = "airmic_stream_channel"
        const val NOTIFICATION_ID = 1001

        const val ACTION_START = "com.airmic.app.ACTION_START"
        const val ACTION_STOP = "com.airmic.app.ACTION_STOP"

        const val EXTRA_HOST = "extra_host"
        const val EXTRA_PORT = "extra_port"
        const val EXTRA_IS_UDP = "extra_is_udp"
        const val EXTRA_NOISE_CANCEL = "extra_noise_cancel"

        var isRunning = false
            private set
    }

    private val binder = LocalBinder()
    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())
    private var streamerJob: Job? = null
    private var streamer: AudioStreamer? = null

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    var onStatusChanged: ((Boolean, String) -> Unit)? = null
    var onLevelUpdate: ((Float, Float) -> Unit)? = null

    inner class LocalBinder : Binder() {
        fun getService(): MicService = this@MicService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()

        val powerManager = getSystemService(Context.POWER_SERVICE) as? PowerManager
        wakeLock = powerManager?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AirMic::WakeLock")

        val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        @Suppress("DEPRECATION")
        wifiLock = wifiManager?.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "AirMic::WifiLock")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopStreaming()
                stopSelf()
            }
            ACTION_START -> {
                val host = intent.getStringExtra(EXTRA_HOST) ?: "192.168.1.100"
                val port = intent.getIntExtra(EXTRA_PORT, 55555)
                val isUdp = intent.getBooleanExtra(EXTRA_IS_UDP, true)
                val noiseCancel = intent.getBooleanExtra(EXTRA_NOISE_CANCEL, true)

                startStreaming(host, port, isUdp, noiseCancel)
            }
        }
        return START_NOT_STICKY
    }

    private fun startStreaming(host: String, port: Int, isUdp: Boolean, noiseCancel: Boolean) {
        if (isRunning) return

        wakeLock?.acquire(12 * 60 * 60 * 1000L) // 12 hours max
        wifiLock?.acquire()

        val notification = buildNotification("Connecting to $host:$port...")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        isRunning = true
        onStatusChanged?.invoke(true, "Streaming live to $host:$port")

        streamer = AudioStreamer(
            host = host,
            port = port,
            isUdp = isUdp,
            enableNoiseSuppressor = noiseCancel,
            onLevelUpdate = { db, normalized ->
                onLevelUpdate?.invoke(db, normalized)
            },
            onError = { err ->
                serviceScope.launch {
                    onStatusChanged?.invoke(false, err)
                    stopStreaming()
                    stopSelf()
                }
            }
        )

        streamerJob = serviceScope.launch(Dispatchers.IO) {
            streamer?.start()
        }

        updateNotification("Streaming microphone to $host:$port (${if (isUdp) "UDP" else "TCP"})")
    }

    fun setGain(gain: Float) {
        streamer?.gain = gain
    }

    fun setMute(muted: Boolean) {
        streamer?.isMuted = muted
    }

    fun stopStreaming() {
        if (!isRunning) return
        isRunning = false

        streamer?.stop()
        streamerJob?.cancel()
        streamer = null
        streamerJob = null

        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
            if (wifiLock?.isHeld == true) wifiLock?.release()
        } catch (e: Exception) {
            // Ignored
        }

        onStatusChanged?.invoke(false, "Disconnected")
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.notification_channel_desc)
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(contentText: String): Notification {
        val launchIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pLaunchIntent = PendingIntent.getActivity(
            this, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, MicService::class.java).apply {
            action = ACTION_STOP
        }
        val pStopIntent = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AirMic — Microphone Active")
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_mic)
            .setContentIntent(pLaunchIntent)
            .setOngoing(true)
            .addAction(R.drawable.ic_stop, "Stop", pStopIntent)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
        manager?.notify(NOTIFICATION_ID, buildNotification(text))
    }

    override fun onDestroy() {
        stopStreaming()
        super.onDestroy()
    }
}
