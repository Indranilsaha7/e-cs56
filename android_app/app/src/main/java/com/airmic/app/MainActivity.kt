package com.airmic.app

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences

    // UI Elements
    private lateinit var tvStatusTitle: TextView
    private lateinit var tvStatusSubtitle: TextView
    private lateinit var viewStatusDot: View
    private lateinit var tvPhoneIp: TextView
    private lateinit var tvSubnetStatus: TextView
    private lateinit var btnScanPc: MaterialButton
    private lateinit var etPcIp: EditText
    private lateinit var etPort: EditText
    private lateinit var rgProtocol: RadioGroup
    private lateinit var rbUdp: RadioButton
    private lateinit var rbTcp: RadioButton
    private lateinit var tvVuDb: TextView
    private lateinit var pbVuMeter: ProgressBar
    private lateinit var tvGainValue: TextView
    private lateinit var sbGain: SeekBar
    private lateinit var switchNoiseCancel: SwitchMaterial
    private lateinit var switchMute: SwitchMaterial
    private lateinit var btnToggleStream: MaterialButton

    private var micService: MicService? = null
    private var isBound = false
    private var myPhoneIp = "127.0.0.1"
    private var remoteTriggerJob: Job? = null

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            val binder = service as MicService.LocalBinder
            micService = binder.getService()
            isBound = true

            micService?.onStatusChanged = { running, message ->
                runOnUiThread {
                    updateUiState(running, message)
                }
            }

            micService?.onLevelUpdate = { db, normalized ->
                runOnUiThread {
                    pbVuMeter.progress = (normalized * 100).toInt()
                    if (db > -75) {
                        tvVuDb.text = String.format("%.1f dB", db)
                    } else {
                        tvVuDb.text = "-∞ dB"
                    }
                }
            }

            updateUiState(MicService.isRunning, if (MicService.isRunning) "Streaming live" else "Ready to Connect")
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            micService = null
            isBound = false
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val recordAudioGranted = results[Manifest.permission.RECORD_AUDIO] ?: false
        if (!recordAudioGranted) {
            Toast.makeText(this, "Microphone permission is required to stream audio", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("airmic_settings", Context.MODE_PRIVATE)

        initViews()
        loadPhoneIp()
        loadSavedSettings()
        checkPermissions()
        setupListeners()
        startRemoteTriggerListener()
    }

    override fun onStart() {
        super.onStart()
        val intent = Intent(this, MicService::class.java)
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    override fun onStop() {
        super.onStop()
        if (isBound) {
            unbindService(serviceConnection)
            isBound = false
        }
    }

    override fun onDestroy() {
        remoteTriggerJob?.cancel()
        super.onDestroy()
    }

    private fun initViews() {
        tvStatusTitle = findViewById(R.id.tvStatusTitle)
        tvStatusSubtitle = findViewById(R.id.tvStatusSubtitle)
        viewStatusDot = findViewById(R.id.viewStatusDot)
        tvPhoneIp = findViewById(R.id.tvPhoneIp)
        tvSubnetStatus = findViewById(R.id.tvSubnetStatus)
        btnScanPc = findViewById(R.id.btnScanPc)
        etPcIp = findViewById(R.id.etPcIp)
        etPort = findViewById(R.id.etPort)
        rgProtocol = findViewById(R.id.rgProtocol)
        rbUdp = findViewById(R.id.rbUdp)
        rbTcp = findViewById(R.id.rbTcp)
        tvVuDb = findViewById(R.id.tvVuDb)
        pbVuMeter = findViewById(R.id.pbVuMeter)
        tvGainValue = findViewById(R.id.tvGainValue)
        sbGain = findViewById(R.id.sbGain)
        switchNoiseCancel = findViewById(R.id.switchNoiseCancel)
        switchMute = findViewById(R.id.switchMute)
        btnToggleStream = findViewById(R.id.btnToggleStream)
    }

    private fun loadPhoneIp() {
        myPhoneIp = NetworkDiscovery.getDeviceWifiIp(this)
        tvPhoneIp.text = myPhoneIp
    }

    private fun loadSavedSettings() {
        // Default to brother's PC IP 192.168.0.103 if not saved yet
        val defaultIp = "192.168.0.103"
        etPcIp.setText(prefs.getString("saved_ip", defaultIp))
        etPort.setText(prefs.getString("saved_port", "55555"))
        val isUdp = prefs.getBoolean("saved_udp", true)
        if (isUdp) rbUdp.isChecked = true else rbTcp.isChecked = true
        val gain = prefs.getInt("saved_gain", 100)
        sbGain.progress = gain
        tvGainValue.text = "$gain%"

        checkSubnetMatch()
    }

    private fun checkSubnetMatch() {
        val pcIp = etPcIp.text.toString().trim()
        val phoneParts = myPhoneIp.split(".")
        val pcParts = pcIp.split(".")

        if (phoneParts.size == 4 && pcParts.size == 4) {
            val sameSubnet = (phoneParts[0] == pcParts[0] && phoneParts[1] == pcParts[1] && phoneParts[2] == pcParts[2])
            if (sameSubnet) {
                tvSubnetStatus.text = "✅ Both devices on same Wi-Fi subnet (${phoneParts[0]}.${phoneParts[1]}.${phoneParts[2]}.x)"
                tvSubnetStatus.setTextColor(ContextCompat.getColor(this, R.color.accent_green))
            } else {
                tvSubnetStatus.text = "⚠️ Subnet mismatch: Phone is on ${phoneParts[0]}.${phoneParts[1]}.${phoneParts[2]}.x, PC is on ${pcParts[0]}.${pcParts[1]}.${pcParts[2]}.x"
                tvSubnetStatus.setTextColor(ContextCompat.getColor(this, R.color.accent_amber))
            }
        } else {
            tvSubnetStatus.text = "Enter valid IPv4 address"
            tvSubnetStatus.setTextColor(ContextCompat.getColor(this, R.color.text_secondary))
        }
    }

    private fun saveSettings() {
        prefs.edit().apply {
            putString("saved_ip", etPcIp.text.toString().trim())
            putString("saved_port", etPort.text.toString().trim())
            putBoolean("saved_udp", rbUdp.isChecked)
            putInt("saved_gain", sbGain.progress)
            apply()
        }
    }

    private fun checkPermissions() {
        val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val needed = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (needed.isNotEmpty()) {
            permissionLauncher.launch(needed.toTypedArray())
        }
    }

    private fun setupListeners() {
        btnScanPc.setOnClickListener {
            performAutoDiscovery()
        }

        etPcIp.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                checkSubnetMatch()
            }
            override fun afterTextChanged(s: Editable?) {
                saveSettings()
            }
        })

        sbGain.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvGainValue.text = "$progress%"
                val gainMultiplier = progress / 100.0f
                micService?.setGain(gainMultiplier)
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                saveSettings()
            }
        })

        switchMute.setOnCheckedChangeListener { _, isChecked ->
            micService?.setMute(isChecked)
            if (isChecked) {
                pbVuMeter.progress = 0
                tvVuDb.text = "MUTED"
            }
        }

        btnToggleStream.setOnClickListener {
            if (MicService.isRunning) {
                stopMicService()
            } else {
                startMicService()
            }
        }
    }

    /**
     * Listens on UDP port 55554 for remote triggers from the PC app.
     */
    private fun startRemoteTriggerListener() {
        remoteTriggerJob = lifecycleScope.launch(Dispatchers.IO) {
            var socket: DatagramSocket? = null
            try {
                socket = DatagramSocket(NetworkDiscovery.DISCOVERY_PORT).apply {
                    soTimeout = 0 // Infinite blocking
                }
                val buffer = ByteArray(2048)
                val packet = DatagramPacket(buffer, buffer.size)

                while (isActive) {
                    try {
                        socket.receive(packet)
                        val text = String(packet.data, 0, packet.length).trim()
                        if (text.startsWith("{") && text.contains("CONNECT_REQUEST")) {
                            val json = JSONObject(text)
                            val pcIp = json.optString("pc_ip", packet.address.hostAddress ?: "")
                            val port = json.optInt("port", 55555)

                            withContext(Dispatchers.Main) {
                                etPcIp.setText(pcIp)
                                etPort.setText(port.toString())
                                checkSubnetMatch()
                                Toast.makeText(this@MainActivity, "Received trigger from PC ($pcIp)! Starting Mic...", Toast.LENGTH_SHORT).show()
                                if (!MicService.isRunning) {
                                    startMicService()
                                }
                            }
                        }
                    } catch (e: Exception) {
                        if (!isActive) break
                    }
                }
            } catch (e: Exception) {
                // Port might be in use during active scan
            } finally {
                socket?.close()
            }
        }
    }

    private fun performAutoDiscovery() {
        btnScanPc.isEnabled = false
        btnScanPc.text = "⏳ Searching for PC..."

        lifecycleScope.launch {
            val server = NetworkDiscovery.discoverPc(applicationContext, timeoutMs = 3500)
            btnScanPc.isEnabled = true
            btnScanPc.text = "🔍 Search for PC on Wi-Fi"

            if (server != null) {
                etPcIp.setText(server.ip)
                etPort.setText(server.port.toString())
                saveSettings()
                checkSubnetMatch()
                Toast.makeText(this@MainActivity, "Found: ${server.pcName} (${server.ip})", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(
                    this@MainActivity,
                    "No AirMic PC found automatically. Make sure PC receiver is running on the same Wi-Fi, or enter IP manually.",
                    Toast.LENGTH_LONG
                ).show()
            }
        }
    }

    private fun startMicService() {
        val ip = etPcIp.text.toString().trim()
        val portStr = etPort.text.toString().trim()

        if (ip.isEmpty()) {
            etPcIp.error = "Please enter PC IP address"
            return
        }

        val port = portStr.toIntOrNull() ?: 55555
        saveSettings()

        val intent = Intent(this, MicService::class.java).apply {
            action = MicService.ACTION_START
            putExtra(MicService.EXTRA_HOST, ip)
            putExtra(MicService.EXTRA_PORT, port)
            putExtra(MicService.EXTRA_IS_UDP, rbUdp.isChecked)
            putExtra(MicService.EXTRA_NOISE_CANCEL, switchNoiseCancel.isChecked)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun stopMicService() {
        val intent = Intent(this, MicService::class.java).apply {
            action = MicService.ACTION_STOP
        }
        startService(intent)
    }

    private fun updateUiState(isStreaming: Boolean, statusMessage: String) {
        if (isStreaming) {
            tvStatusTitle.text = "Microphone Live"
            tvStatusSubtitle.text = statusMessage
            viewStatusDot.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.accent_green))

            btnToggleStream.text = "⏹️ STOP MICROPHONE"
            btnToggleStream.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.accent_red))

            etPcIp.isEnabled = false
            etPort.isEnabled = false
            rbUdp.isEnabled = false
            rbTcp.isEnabled = false
            btnScanPc.isEnabled = false
        } else {
            tvStatusTitle.text = "Ready to Connect"
            tvStatusSubtitle.text = statusMessage
            viewStatusDot.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.accent_amber))

            btnToggleStream.text = "🎙️ START MICROPHONE"
            btnToggleStream.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.accent_green))

            etPcIp.isEnabled = true
            etPort.isEnabled = true
            rbUdp.isEnabled = true
            rbTcp.isEnabled = true
            btnScanPc.isEnabled = true

            pbVuMeter.progress = 0
            tvVuDb.text = "-∞ dB"
        }
    }
}
