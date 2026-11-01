package com.hydro.app.core.network

import com.squareup.moshi.Json

/**
 * Страница пагинатора Laravel (`data.current_page` + `data.data`).
 * Списки теплиц, зон, узлов и алертов приходят в этом виде, не плоским массивом.
 */
data class LaravelPage<T>(
    val data: List<T> = emptyList(),
    @Json(name = "current_page") val currentPage: Int = 1,
    @Json(name = "last_page") val lastPage: Int = 1,
    val total: Int? = null,
)
