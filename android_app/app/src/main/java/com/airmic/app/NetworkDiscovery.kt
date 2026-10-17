package com.airmic.app

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.util.Collections
import java.util.Locale

data class DiscoveredServer(
    val ip: String,
    val port: Int,
    val pcName: String
)

object NetworkDiscovery {
    const val DISCOVERY_PORT = 55554
    const val AUDIO_PORT = 55555

    /**
     * Determines the active Wi-Fi IPv4 address of this Android phone.
     */
    fun getDeviceWifiIp(context: Context): String {
        try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            val ipInt = wifi?.connectionInfo?.ipAddress ?: 0
            if (ipInt != 0) {
                return String.format(
                    Locale.US,
                    "%d.%d.%d.%d",
                    ipInt and 0xff,
                    ipInt shr 8 and 0xff,
                    ipInt shr 16 and 0xff,
                    ipInt shr 24 and 0xff
                )
            }
        } catch (e: Exception) {
            // Fallback
        }

        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            for (nInt in Collections.list(interfaces)) {
                if (nInt.isLoopback || !nInt.isUp) continue
                for (addr in Collections.list(nInt.inetAddresses)) {
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        val host = addr.hostAddress ?: ""
                        if (!host.startsWith("127.")) {
                            return host
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // Ignored
        }
        return "127.0.0.1"
    }

    suspend fun discoverPc(context: Context, timeoutMs: Long = 3500): DiscoveredServer? = withContext(Dispatchers.IO) {
        var socket: DatagramSocket? = null
        var multicastLock: WifiManager.MulticastLock? = null

        try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            multicastLock = wifi?.createMulticastLock("airmic_discovery")
            multicastLock?.setReferenceCounted(true)
            multicastLock?.acquire()

            socket = DatagramSocket(DISCOVERY_PORT).apply {
                broadcast = true
                soTimeout = timeoutMs.toInt()
            }

            // Send discovery probe broadcast with our phone IP
            val phoneIp = getDeviceWifiIp(context)
            val probeJson = JSONObject().apply {
                put("protocol", "AIRMIC")
                put("type", "DISCOVER")
                put("phone_ip", phoneIp)
            }
            val probeBytes = probeJson.toString().toByteArray()

            // 1. Broadcast to global 255.255.255.255
            try {
                val broadcastAddr = InetAddress.getByName("255.255.255.255")
                socket.send(DatagramPacket(probeBytes, probeBytes.size, broadcastAddr, DISCOVERY_PORT))
            } catch (e: Exception) {
                // Ignored
            }

            // 2. Broadcast to specific subnet broadcast (e.g. 192.168.0.255)
            try {
                val parts = phoneIp.split(".")
                if (parts.size == 4) {
                    val subnetBcast = "${parts[0]}.${parts[1]}.${parts[2]}.255"
                    val subnetAddr = InetAddress.getByName(subnetBcast)
                    socket.send(DatagramPacket(probeBytes, probeBytes.size, subnetAddr, DISCOVERY_PORT))
                }
            } catch (e: Exception) {
                // Ignored
            }

            // Listen for beacon or reply
            val buffer = ByteArray(2048)
            val receivePacket = DatagramPacket(buffer, buffer.size)

            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < timeoutMs) {
                try {
                    socket.receive(receivePacket)
                    val rawStr = String(receivePacket.data, 0, receivePacket.length).trim()
                    if (rawStr.startsWith("{") && rawStr.contains("AIRMIC")) {
                        val json = JSONObject(rawStr)
                        val type = json.optString("type")
                        if (type == "BEACON" || type == "ACK") {
                            val ip = json.optString("ip", receivePacket.address.hostAddress ?: "")
                            val port = json.optInt("audio_port", AUDIO_PORT)
                            val name = json.optString("pc_name", "AirMic PC")
                            return@withContext DiscoveredServer(ip, port, name)
                        }
                    }
                } catch (e: Exception) {
                    break
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            try {
                multicastLock?.release()
            } catch (e: Exception) {
                // Ignored
            }
            socket?.close()
        }
        return@withContext null
    }
}
