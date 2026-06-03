package com.hydro.app.core.i18n

import android.content.Context
import com.squareup.moshi.Moshi
import com.squareup.moshi.adapter
import java.util.Locale

data class HumanErrorInput(
    val code: String? = null,
    val message: String? = null,
    val humanMessage: String? = null,
)

class ErrorCatalog private constructor(
    private val messagesByCode: Map<String, String>,
) {
    fun resolve(input: HumanErrorInput, fallback: String? = null): String {
        val human = input.humanMessage?.trim().orEmpty()
        if (human.isNotEmpty()) {
            return human
        }

        val rawMessage = input.message?.trim().orEmpty()
        if (rawMessage.isNotEmpty() && containsCyrillic(rawMessage)) {
            return rawMessage
        }

        val normalizedCode = normalizeCode(input.code)
        if (normalizedCode.isNotEmpty()) {
            messagesByCode[normalizedCode]?.let { return it }
        }

        if (rawMessage.isNotEmpty()) {
            val fromMessageAsCode = normalizeCode(rawMessage)
            if (fromMessageAsCode.isNotEmpty()) {
                messagesByCode[fromMessageAsCode]?.let { return it }
            }
            return rawMessage
        }

        if (normalizedCode.isNotEmpty()) {
            return "Внутренняя ошибка системы (код: $normalizedCode)."
        }

        return fallback ?: GENERIC_MESSAGE
    }

    fun resolveHttpStatus(statusCode: Int): String {
        return when (statusCode) {
            401 -> resolve(HumanErrorInput(code = "unauthenticated"))
            403 -> resolve(HumanErrorInput(code = "forbidden"))
            404 -> resolve(HumanErrorInput(code = "not_found"))
            422 -> resolve(HumanErrorInput(code = "validation_error"))
            429 -> resolve(HumanErrorInput(code = "rate_limit_exceeded"))
            in 500..599 -> resolve(HumanErrorInput(code = "service_unavailable"))
            else -> resolve(HumanErrorInput(code = "internal_error"))
        }
    }

    companion object {
        const val GENERIC_MESSAGE = "Произошла ошибка. Проверьте логи сервиса или обратитесь к администратору."

        fun load(context: Context, moshi: Moshi): ErrorCatalog {
            return ErrorCatalog(loadMessages(context, moshi))
        }

        fun createForTest(messagesByCode: Map<String, String>): ErrorCatalog {
            return ErrorCatalog(messagesByCode)
        }

        fun normalizeCode(raw: String?): String {
            return raw
                ?.trim()
                ?.lowercase(Locale.ROOT)
                ?.replace(Regex("[^a-z0-9_]"), "_")
                ?.trim('_')
                .orEmpty()
        }

        @OptIn(ExperimentalStdlibApi::class)
        private fun loadMessages(context: Context, moshi: Moshi): Map<String, String> {
            return try {
                val json = context.assets.open("i18n/error_codes.json").bufferedReader().use { it.readText() }
                val catalog = moshi.adapter<ErrorCatalogFile>().fromJson(json) ?: return emptyMap()
                catalog.codes
                    .mapNotNull { entry ->
                        val code = normalizeCode(entry.code)
                        val message = entry.message?.trim().orEmpty()
                        if (code.isEmpty() || message.isEmpty()) {
                            null
                        } else {
                            code to message
                        }
                    }
                    .toMap()
            } catch (_: Exception) {
                emptyMap()
            }
        }

        private fun containsCyrillic(value: String): Boolean {
            return value.any { char ->
                char in '\u0400'..'\u04FF' || char == 'ё' || char == 'Ё'
            }
        }
    }
}
