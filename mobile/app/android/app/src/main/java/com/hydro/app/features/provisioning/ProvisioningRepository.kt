package com.hydro.app.features.provisioning

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
	private val client: OkHttpClient
) {
	suspend fun sendProvision(
		host: String = "http://192.168.4.1/api/provision",
		wifiSsid: String,
		wifiPassword: String,
		backendUrl: String,
		ghUid: String,
		zoneUid: String
	): Result<Unit> = withContext(Dispatchers.IO) {
		runCatching {
			val json = JSONObject()
				.put("wifi_ssid", wifiSsid)
				.put("wifi_password", wifiPassword)
				.put("backend_base_url", backendUrl)
				.put("gh_uid", ghUid)
				.put("zone_uid", zoneUid)
				.toString()
			val body = json.toRequestBody("application/json".toMediaType())
			val req = Request.Builder().url(host).post(body).build()
			client.newCall(req).execute().use { resp ->
				if (!resp.isSuccessful) error("Provision failed: ${'$'}{resp.code}")
			}
		}
	}
}


