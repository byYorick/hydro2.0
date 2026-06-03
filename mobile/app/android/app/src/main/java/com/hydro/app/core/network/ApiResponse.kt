package com.hydro.app.core.network

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ApiResponse<T>(
    val status: String,
    @Json(name = "data") val data: T? = null,
    val message: String? = null,
    /** snake_case код ошибки API (фаза 2). */
    val code: String? = null,
    @Json(name = "human_error_message") val humanErrorMessage: String? = null,
    val title: String? = null,
    val errors: Map<String, List<String>>? = null,
)

