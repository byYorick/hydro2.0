package com.hydro.app.core.i18n

import android.content.Context
import com.squareup.moshi.Moshi
import com.squareup.moshi.adapter

class AlertCatalog private constructor(
    private val descriptionsByCode: Map<String, String>,
    private val titlesByCode: Map<String, String>,
) {
    fun resolveMessage(code: String?, fallbackMessage: String?): String {
        val normalized = ErrorCatalog.normalizeCode(code)
        if (normalized.isNotEmpty()) {
            descriptionsByCode[normalized]?.let { return it }
            titlesByCode[normalized]?.let { return it }
        }

        val fallback = fallbackMessage?.trim().orEmpty()
        if (fallback.isNotEmpty()) {
            return fallback
        }

        return if (normalized.isNotEmpty()) {
            "Событие требует проверки (код: $normalized)."
        } else {
            ErrorCatalog.GENERIC_MESSAGE
        }
    }

    companion object {
        fun load(context: Context, moshi: Moshi): AlertCatalog {
            return try {
                val json = context.assets.open("i18n/alert_codes.json").bufferedReader().use { it.readText() }
                val catalog = moshi.adapter<AlertCatalogFile>().fromJson(json) ?: return empty()
                val descriptions = mutableMapOf<String, String>()
                val titles = mutableMapOf<String, String>()
                for (entry in catalog.codes) {
                    val code = ErrorCatalog.normalizeCode(entry.code)
                    if (code.isEmpty()) {
                        continue
                    }
                    entry.description?.trim()?.takeIf { it.isNotEmpty() }?.let { descriptions[code] = it }
                    entry.title?.trim()?.takeIf { it.isNotEmpty() }?.let { titles[code] = it }
                }
                AlertCatalog(descriptions, titles)
            } catch (_: Exception) {
                empty()
            }
        }

        fun empty(): AlertCatalog = AlertCatalog(emptyMap(), emptyMap())

        fun createForTest(descriptions: Map<String, String>): AlertCatalog {
            return AlertCatalog(descriptions, emptyMap())
        }
    }
}
