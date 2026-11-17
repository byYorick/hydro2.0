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

fun operatorStatusLabel(raw: String?): String = when (raw?.trim()?.lowercase()) {
    null, "", "—" -> "Нет данных"
    "ok", "healthy", "normal" -> "Норма"
    "online" -> "На связи"
    "offline", "disconnected", "lost" -> "Нет связи"
    "active" -> "Активно"
    "running" -> "Выполняется"
    "ready" -> "Готово"
    "idle" -> "Ожидание"
    "paused" -> "Пауза"
    "stopped" -> "Остановлено"
    "warning", "degraded" -> "Требует внимания"
    "critical", "alarm", "alert" -> "Тревога"
    "error", "failed" -> "Ошибка"
    "estop", "emergency" -> "Аварийная остановка"
    "auto" -> "Автоматический режим"
    "semi" -> "Полуавтоматический режим"
    "manual" -> "Ручной режим"
    "info" -> "Информация"
    "resolved", "closed" -> "Закрыто"
    "pending" -> "Ожидает обработки"
    "configured" -> "Настроено"
    "configuring", "provisioning" -> "Настраивается"
    "unprovisioned" -> "Не настроено"
    "registered" -> "Зарегистрировано"
    else -> if (raw.orEmpty().any { it in '\u0400'..'\u04ff' }) raw.orEmpty() else "Статус неизвестен"
}

fun operatorStageLabel(raw: String): String = when (raw.lowercase()) {
    "idle" -> "Ожидание"
    "ready", "complete_ready" -> "Готовность к поливу"
    "startup", "preparing", "setup_pending" -> "Подготовка системы"
    "clean_fill_start", "clean_fill", "clean_fill_check" -> "Набор чистой воды"
    "solution_fill_start", "solution_fill", "solution_fill_check", "tank_filling" -> "Набор раствора"
    "prepare_recirculation_start", "prepare_recirculation_check", "tank_recirc" -> "Перемешивание и подготовка раствора"
    "await_ready" -> "Ожидание готовности раствора"
    "decision_gate" -> "Проверка условий полива"
    "irrigation_start", "irrigation_check", "irrigating" -> "Полив"
    "irrigation_stop" -> "Остановка полива"
    "irrigation_recovery_check", "irrig_recirc" -> "Восстановление после полива"
    "completed_skip" -> "Полив пропущен"
    "manual_hold" -> "Ожидание действия оператора"
    "failed", "error" -> "Остановка из-за ошибки"
    else -> if (raw.any { it in '\u0400'..'\u04ff' }) raw else "Этап не распознан"
}

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
