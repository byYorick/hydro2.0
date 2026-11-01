package com.hydro.app.core.domain

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class NamedRef(
    val id: Int? = null,
    val uid: String? = null,
    val name: String? = null,
    val status: String? = null,
)

@JsonClass(generateAdapter = true)
data class Greenhouse(
    val id: Int,
    val uid: String = "",
    val name: String = "",
    val location: String? = null,
    val status: String? = null,
    @Json(name = "zones_count") val zonesCount: Int? = null,
    val timezone: String? = null,
    val type: String? = null,
    val description: String? = null,
)

@JsonClass(generateAdapter = true)
data class Zone(
    val id: Int,
    val uid: String = "",
    val name: String = "",
    @Json(name = "greenhouse_id") val greenhouseId: Int = 0,
    @Json(name = "greenhouse_uid") val greenhouseUid: String? = null,
    val status: String? = null,
    val culture: String? = null,
    @Json(name = "recipe_id") val recipeId: Int? = null,
    @Json(name = "recipe_name") val recipeName: String? = null,
    @Json(name = "health_status") val healthStatus: String? = null,
    @Json(name = "health_score") val healthScore: Double? = null,
    @Json(name = "control_mode") val controlMode: String? = null,
    @Json(name = "nodes_count") val nodesCount: Int? = null,
    @Json(name = "water_state") val waterState: String? = null,
    val description: String? = null,
    val greenhouse: NamedRef? = null,
)

@JsonClass(generateAdapter = true)
data class NodeChannel(
    val id: Int? = null,
    val channel: String? = null,
    val type: String? = null,
    val metric: String? = null,
    val unit: String? = null,
)

@JsonClass(generateAdapter = true)
data class Node(
    val id: Int,
    val uid: String = "",
    val name: String = "",
    val type: String = "",
    val status: String? = null,
    @Json(name = "zone_id") val zoneId: Int? = null,
    @Json(name = "zone_uid") val zoneUid: String? = null,
    val rssi: Int? = null,
    @Json(name = "fw_version") val firmware: String? = null,
    @Json(name = "uptime_seconds") val uptime: Long? = null,
    @Json(name = "last_seen_at") val lastSeenAt: String? = null,
    @Json(name = "lifecycle_state") val lifecycleState: String? = null,
    val channels: List<NodeChannel>? = null,
    val zone: NamedRef? = null,
)

/**
 * Снимок зоны из `GET /api/zones/{id}/telemetry/last`.
 * Канонические ключи: ph, ec, temperature, humidity, co2, last_updated.
 * Уровень раствора в этот снимок backend не кладёт.
 */
@JsonClass(generateAdapter = true)
data class TelemetryLast(
    @Json(name = "zone_id") val zoneId: Int? = null,
    val ph: Double? = null,
    val ec: Double? = null,
    val temperature: Double? = null,
    val humidity: Double? = null,
    val co2: Double? = null,
    @Json(name = "last_updated") val lastUpdated: String? = null,
    @Json(name = "temp_air") val airTemp: Double? = null,
    @Json(name = "humidity_air") val airHumidity: Double? = null,
    @Json(name = "temp_solution") val solutionTemp: Double? = null,
    @Json(name = "light_level") val lightLevel: Double? = null,
) {
    val airTemperature: Double? get() = temperature ?: airTemp
    val airHumidityPercent: Double? get() = humidity ?: airHumidity
}

@JsonClass(generateAdapter = true)
data class TelemetryHistoryPoint(
    val timestamp: String = "",
    val ts: String? = null,
    val value: Double? = null,
    val channel: String? = null,
    @Json(name = "metric_type") val metricType: String? = null,
) {
    val whenText: String get() = ts ?: timestamp
}

@JsonClass(generateAdapter = true)
data class NodeTelemetrySample(
    @Json(name = "metric_type") val metricType: String? = null,
    val channel: String? = null,
    val value: Double? = null,
    val ts: String? = null,
    val quality: String? = null,
)

@JsonClass(generateAdapter = true)
data class Alert(
    val id: Int,
    val level: String = "info",
    val type: String = "",
    val severity: String? = null,
    val code: String? = null,
    val title: String? = null,
    @Json(name = "zone_id") val zoneId: Int? = null,
    @Json(name = "zone_name") val zoneName: String? = null,
    val zone: NamedRef? = null,
    @Json(name = "node_id") val nodeId: Int? = null,
    @Json(name = "node_uid") val nodeUid: String? = null,
    @Json(name = "node_name") val nodeName: String? = null,
    val message: String = "",
    val timestamp: String = "",
    @Json(name = "created_at") val createdAt: String? = null,
    val status: String? = null,
    @Json(name = "acknowledged_at") val acknowledgedAt: String? = null,
    @Json(name = "resolved_at") val resolvedAt: String? = null,
) {
    val displayLevel: String get() = (severity ?: level).ifBlank { "info" }
    val displayTime: String get() = createdAt ?: timestamp
    val displayZone: String? get() = zoneName ?: zone?.name
    val displayMessage: String
        get() = message.ifBlank { title ?: code ?: type }.ifBlank { "Событие" }
    val isActive: Boolean get() = status.equals("ACTIVE", ignoreCase = true)
}

@JsonClass(generateAdapter = true)
data class CommandParams(
    @Json(name = "duration_sec") val durationSec: Int? = null,
    val state: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class CommandRequest(
    val type: String,
    val params: CommandParams? = null,
    @Json(name = "node_uid") val nodeUid: String? = null,
    val channel: String? = null,
)

@JsonClass(generateAdapter = true)
data class NodeCommandRequest(
    val cmd: String,
    val channel: String? = null,
    val params: CommandParams? = null,
)

@JsonClass(generateAdapter = true)
data class CommandResponse(
    @Json(name = "command_id") val commandId: String? = null,
    @Json(name = "cmd_id") val cmdId: String? = null,
    val status: String? = null,
    val ts: Long? = null,
    @Json(name = "error_code") val errorCode: String? = null,
    @Json(name = "error_message") val errorMessage: String? = null,
    @Json(name = "human_error_message") val humanErrorMessage: String? = null,
) {
    val resolvedId: String? get() = commandId ?: cmdId
}

@JsonClass(generateAdapter = true)
data class ControlModeData(
    @Json(name = "control_mode") val controlMode: String? = null,
    @Json(name = "current_stage") val currentStage: String? = null,
    @Json(name = "workflow_phase") val workflowPhase: String? = null,
    @Json(name = "pending_manual_step") val pendingManualStep: String? = null,
)

@JsonClass(generateAdapter = true)
data class ControlModeRequest(
    @Json(name = "control_mode") val controlMode: String,
    val source: String = "android_operator",
    val reason: String? = null,
)

@JsonClass(generateAdapter = true)
data class User(
    val id: Int,
    val name: String,
    val email: String,
    val role: String? = null,
    val roles: List<String>? = null,
)

@JsonClass(generateAdapter = true)
data class LoginResponseData(
    val token: String,
    val user: User,
)

data class LevelReading(
    val label: String,
    val valueText: String,
    val metric: String,
)
