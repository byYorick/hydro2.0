package com.hydro.app.core.network

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ApiResponse<T>(
    val status: String,
    @Json(name = "data") val data: T? = null,
    val message: String? = null,
    val code: Int? = null,
    val errors: Map<String, List<String>>? = null
)

