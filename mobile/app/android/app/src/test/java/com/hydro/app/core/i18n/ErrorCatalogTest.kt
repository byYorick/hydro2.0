package com.hydro.app.core.i18n

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ErrorCatalogTest {
    private val catalog = ErrorCatalog.createForTest(
        mapOf(
            "not_found" to "Запрошенный объект не найден.",
            "timeout" to "Превышено время ожидания выполнения команды.",
        ),
    )

    @Test
    fun resolve_prefers_human_error_message() {
        val message = catalog.resolve(
            HumanErrorInput(
                code = "timeout",
                message = "TIMEOUT",
                humanMessage = "Превышено время ожидания выполнения команды.",
            ),
        )
        assertEquals("Превышено время ожидания выполнения команды.", message)
    }

    @Test
    fun resolve_uses_catalog_by_snake_case_code() {
        val message = catalog.resolve(
            HumanErrorInput(code = "NOT_FOUND", message = "not found"),
        )
        assertEquals("Запрошенный объект не найден.", message)
    }

    @Test
    fun resolve_keeps_raw_message_when_code_unknown() {
        val message = catalog.resolve(
            HumanErrorInput(code = "unknown_xyz", message = "Something went wrong"),
        )
        assertEquals("Something went wrong", message)
    }

    @Test
    fun resolve_uses_code_fallback_when_message_missing() {
        val message = catalog.resolve(HumanErrorInput(code = "unknown_xyz"))
        assertEquals("Внутренняя ошибка системы (код: unknown_xyz).", message)
    }

    @Test
    fun normalize_code_converts_upper_snake() {
        assertEquals("cycle_already_active", ErrorCatalog.normalizeCode("CYCLE_ALREADY_ACTIVE"))
    }
}
