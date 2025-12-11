package com.hydro.app.features.provisioning

import android.content.Context
import android.net.wifi.WifiManager
import android.net.wifi.ScanResult
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
    private val client: OkHttpClient,
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
        config: ProvisioningViewModel.ProvisioningConfig,
        backendUrl: String
    ): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            // Default IP for ESP32 AP mode
            val deviceIp = device.ipAddress ?: "192.168.4.1"
            val url = "http://$deviceIp/api/provision"
            
            val json = JSONObject()
                .put("wifi_ssid", config.wifiSsid)
                .put("wifi_password", config.wifiPassword)
                .put("backend_base_url", backendUrl)
            if (config.greenhouseUid != null) {
                json.put("gh_uid", config.greenhouseUid)
            }
            if (config.zoneUid != null) {
                json.put("zone_uid", config.zoneUid)
            }
            json.put("node_name", config.nodeName)
            
            val body = json.toString().toRequestBody("application/json".toMediaType())
            val req = Request.Builder()
                .url(url)
                .post(body)
                .build()
            
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    error("Provision failed: ${resp.code} - ${resp.body?.string()}")
                }
            }
        }
    }
}
