package com.hydro.app.core.network

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/**
 * Тело ошибки Laravel API (фаза 2: human_error_message).
 */
@JsonClass(generateAdapter = true)
data class ApiErrorBody(
    val status: String? = null,
    val code: String? = null,
    val message: String? = null,
    @Json(name = "human_error_message") val humanErrorMessage: String? = null,
    val title: String? = null,
    val errors: Map<String, List<String>>? = null,
)
