package com.hydro.app.core.network

import com.hydro.app.core.config.CleartextPolicy
import com.hydro.app.core.config.ServerEndpoint
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException

/**
 * Подменяет scheme/host/port каждого запроса адресом из настроек оператора.
 * Retrofit создаётся с фиктивным baseUrl, реальный адрес живёт в DataStore.
 */
class DynamicBaseUrlInterceptor(
    private val endpointProvider: () -> ServerEndpoint,
    private val cleartextAllowed: (ServerEndpoint) -> Boolean = { endpoint ->
        CleartextPolicy.allows(endpoint, debugBuild = true, allowCleartextFlag = false)
    },
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val endpoint = endpointProvider()
        if (!cleartextAllowed(endpoint)) {
            throw IOException(CleartextPolicy.rejectionMessage())
        }
        val rewritten = chain.request().url.newBuilder()
            .scheme(if (endpoint.useHttps) "https" else "http")
            .host(endpoint.host)
            .port(endpoint.port)
            .build()
        return chain.proceed(chain.request().newBuilder().url(rewritten).build())
    }

    companion object {
        /** Фиктивный baseUrl Retrofit. Реальный адрес задаёт интерсептор. */
        const val PLACEHOLDER_BASE_URL = "http://127.0.0.1/"

        fun placeholder(): okhttp3.HttpUrl = PLACEHOLDER_BASE_URL.toHttpUrl()
    }
}
