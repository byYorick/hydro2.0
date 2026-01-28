package com.hydro.app.core.domain

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class Greenhouse(
    val id: Int,
    val uid: String,
    val name: String,
    val location: String? = null,
    val status: String? = null,
    @Json(name = "zones_count") val zonesCount: Int? = null
)

@JsonClass(generateAdapter = true)
data class Zone(
    val id: Int,
    val uid: String,
    val name: String,
    @Json(name = "greenhouse_id") val greenhouseId: Int,
    @Json(name = "greenhouse_uid") val greenhouseUid: String? = null,
    val status: String? = null,
    val culture: String? = null,
    @Json(name = "recipe_id") val recipeId: Int? = null,
    @Json(name = "recipe_name") val recipeName: String? = null
)

@JsonClass(generateAdapter = true)
data class Node(
    val id: Int,
    val uid: String,
    val name: String,
    val type: String,
    val status: String? = null,
    @Json(name = "zone_id") val zoneId: Int? = null,
    @Json(name = "zone_uid") val zoneUid: String? = null,
    val rssi: Int? = null,
    val firmware: String? = null,
    val uptime: Long? = null
)

@JsonClass(generateAdapter = true)
data class TelemetryLast(
    @Json(name = "zone_id") val zoneId: Int,
    val ph: Double? = null,
    val ec: Double? = null,
    @Json(name = "temp_air") val airTemp: Double? = null,
    @Json(name = "humidity_air") val airHumidity: Double? = null,
    @Json(name = "temp_solution") val solutionTemp: Double? = null,
    @Json(name = "light_level") val lightLevel: Double? = null
)

@JsonClass(generateAdapter = true)
data class TelemetryHistoryPoint(
    val timestamp: String,
    val value: Double
)

@JsonClass(generateAdapter = true)
data class Alert(
    val id: Int,
    val level: String,
    val type: String,
    @Json(name = "zone_id") val zoneId: Int? = null,
    @Json(name = "zone_name") val zoneName: String? = null,
    @Json(name = "node_id") val nodeId: Int? = null,
    @Json(name = "node_name") val nodeName: String? = null,
    val message: String,
    val timestamp: String,
    val status: String? = null,
    @Json(name = "acknowledged_at") val acknowledgedAt: String? = null
)

@JsonClass(generateAdapter = true)
data class CommandRequest(
    val type: String,
    val payload: Map<String, Any>? = null
)

@JsonClass(generateAdapter = true)
data class CommandResponse(
    @Json(name = "cmd_id") val cmdId: String,
    val status: String,
    val ts: Long? = null,
    @Json(name = "error_code") val errorCode: String? = null,
    @Json(name = "error_message") val errorMessage: String? = null
)

@JsonClass(generateAdapter = true)
data class User(
    val id: Int,
    val name: String,
    val email: String,
    val roles: List<String>? = null
)

@JsonClass(generateAdapter = true)
data class LoginResponseData(
    val token: String,
    val user: User
)
