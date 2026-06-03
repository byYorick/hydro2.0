package com.hydro.app.core.i18n

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ErrorCatalogFile(
    val codes: List<ErrorCatalogEntry> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class ErrorCatalogEntry(
    val code: String,
    val title: String? = null,
    val message: String? = null,
)

@JsonClass(generateAdapter = true)
data class AlertCatalogFile(
    val codes: List<AlertCatalogEntry> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class AlertCatalogEntry(
    val code: String,
    val title: String? = null,
    val description: String? = null,
)
