package com.hydro.app.features.provisioning

import android.content.Context
import android.net.wifi.WifiManager
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ProvisioningRepository @Inject constructor(
    @com.hydro.app.core.di.ProvisioningClient private val client: OkHttpClient,
    private val setupNetwork: ProvisioningNetwork,
    @ApplicationContext private val context: Context
) {
    suspend fun scanForDevices(): List<ProvisioningViewModel.ProvisioningDevice> = withContext(Dispatchers.IO) {
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val scanResults = wifiManager.scanResults
        
        scanResults
            .filter { it.SSID.startsWith("HYDRO-NODE-", ignoreCase = true) || 
                      it.SSID.startsWith("HYDRO-SETUP", ignoreCase = true) }
            .map { result ->
                ProvisioningViewModel.ProvisioningDevice(
                    ssid = result.SSID,
                    ipAddress = null // Will be determined when connecting
                )
            }
    }

    suspend fun provisionDevice(
        device: ProvisioningViewModel.ProvisioningDevice,
        config: ProvisioningViewModel.ProvisioningConfig
    ): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            require(device.ipAddress == null || device.ipAddress == "192.168.4.1") { "Unsupported setup address" }
            val url = "http://192.168.4.1/wifi/connect"
            require(config.mqttHost.matches(Regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$")) &&
                config.mqttHost.split('.').all { it.toInt() in 0..255 }) { "MQTT host must be an IPv4 address" }
            require(config.mqttPort in 1..65535) { "Invalid MQTT port" }
            val json = JSONObject()
                .put("ssid", config.wifiSsid)
                .put("password", config.wifiPassword)
                .put("mqtt_host", config.mqttHost)
                .put("mqtt_port", config.mqttPort)

            val body = json.toString().toRequestBody("application/json".toMediaType())
            val req = Request.Builder()
                .url(url)
                .post(body)
                .build()
            
            setupNetwork.bind(client).newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    error("Provision failed: ${resp.code}")
                }
            }
        }
    }
}
