package com.hydro.app.core.domain

data class Greenhouse(val id: String, val name: String)
data class Zone(val id: String, val name: String, val greenhouseId: String)
data class TelemetryLast(val zoneId: String, val ph: Double?, val ec: Double?, val airTemp: Double?, val airHumidity: Double?)
data class Alert(val id: String, val level: String, val type: String, val zoneId: String, val timestamp: String, val message: String)


