package com.hydro.app.core.domain

/**
 * Уровень раствора не входит в снимок `telemetry/last` зоны.
 * Ищем его в телеметрии узлов (`metric_type` / channel содержит level).
 */
fun levelReading(samples: List<NodeTelemetrySample>): LevelReading? {
    val sample = samples.firstOrNull { row ->
        val metric = row.metricType.orEmpty()
        val channel = row.channel.orEmpty()
        metric.contains("level", ignoreCase = true) || channel.contains("level", ignoreCase = true)
    } ?: return null

    val metric = sample.metricType ?: sample.channel ?: "LEVEL"
    val isSwitch = metric.contains("switch", ignoreCase = true) ||
        sample.channel.orEmpty().contains("switch", ignoreCase = true)
    val value = sample.value
    val text = when {
        value == null -> "—"
        isSwitch -> if (value >= 0.5) "замкнут" else "разомкнут"
        else -> String.format(java.util.Locale.US, "%.1f", value)
    }
    return LevelReading(
        label = if (isSwitch) "Датчик уровня" else "Уровень",
        valueText = text,
        metric = metric,
    )
}

enum class StatusTone { Ok, Warning, Critical, Offline, Unknown }

fun statusTone(raw: String?): StatusTone {
    val value = raw?.trim()?.lowercase().orEmpty()
    return when (value) {
        "", "unknown" -> StatusTone.Unknown
        "ok", "online", "healthy", "normal", "active", "running", "ready" -> StatusTone.Ok
        "warning", "degraded", "semi" -> StatusTone.Warning
        "critical", "error", "alert", "alarm", "estop", "emergency", "failed" -> StatusTone.Critical
        "offline", "disconnected", "lost", "manual" -> if (value == "manual") StatusTone.Warning else StatusTone.Offline
        else -> StatusTone.Unknown
    }
}
