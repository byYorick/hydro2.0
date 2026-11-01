package com.hydro.app.core.network

import com.hydro.app.core.config.ServerEndpoint
import com.hydro.app.core.data.GreenhousesApi
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.json.LenientNumberAdapters
import com.hydro.app.features.auth.data.AuthApi
import com.hydro.app.features.auth.data.LoginRequest
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class LaravelContractTest {
    @Test
    fun interceptorRewritesHostAndLoginParsesSanctumToken() {
        val server = MockWebServer()
        server.enqueue(
            MockResponse().setBody(
                """
                {"status":"ok","data":{"token":"1|abc","user":{"id":4,"name":"Оператор","email":"operator@example.com","role":"operator","roles":["operator"]}}}
                """.trimIndent(),
            ),
        )
        server.start()
        try {
            val endpoint = ServerEndpoint(server.hostName, server.port, useHttps = false)
            val client = OkHttpClient.Builder()
                .addInterceptor(DynamicBaseUrlInterceptor(endpointProvider = { endpoint }))
                .build()
            val api = retrofit(client).create(AuthApi::class.java)
            val response = runBlocking { api.login(LoginRequest("operator@example.com", "password")) }
            val recorded = server.takeRequest()
            assertEquals("/api/auth/login", recorded.path)
            assertEquals("1|abc", response.data?.token)
            assertEquals("operator", response.data?.user?.role)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun greenhouseListUnwrapsLaravelPaginator() {
        val server = MockWebServer()
        server.enqueue(
            MockResponse().setBody(
                """
                {"status":"ok","data":{"current_page":1,"data":[{"id":2,"uid":"gh-main","name":"Блок A","timezone":"Europe/Moscow","description":"север"}],"total":1}}
                """.trimIndent(),
            ),
        )
        server.start()
        try {
            val endpoint = ServerEndpoint(server.hostName, server.port, useHttps = false)
            val client = OkHttpClient.Builder()
                .addInterceptor(DynamicBaseUrlInterceptor(endpointProvider = { endpoint }))
                .build()
            val api = retrofit(client).create(GreenhousesApi::class.java)
            val page = runBlocking { api.list() }
            val house: Greenhouse = page.data!!.data.single()
            assertEquals("Блок A", house.name)
            assertEquals("Europe/Moscow", house.timezone)
            assertEquals(1, page.data?.total)
        } finally {
            server.shutdown()
        }
    }

    @Test
    fun releasePolicyBlocksCleartextBeforeRequest() {
        val server = MockWebServer()
        server.start()
        try {
            val endpoint = ServerEndpoint(server.hostName, server.port, useHttps = false)
            val client = OkHttpClient.Builder()
                .addInterceptor(
                    DynamicBaseUrlInterceptor(
                        endpointProvider = { endpoint },
                        cleartextAllowed = { false },
                    ),
                )
                .build()
            val api = retrofit(client).create(GreenhousesApi::class.java)
            val error = runCatching { runBlocking { api.list() } }.exceptionOrNull()
            assertTrue(error?.message?.contains("HTTP без TLS") == true || error?.cause?.message?.contains("HTTP без TLS") == true)
            assertEquals(0, server.requestCount)
        } finally {
            server.shutdown()
        }
    }

    private fun retrofit(client: OkHttpClient): Retrofit {
        val moshi = Moshi.Builder()
            .add(LenientNumberAdapters)
            .addLast(KotlinJsonAdapterFactory())
            .build()
        return Retrofit.Builder()
            .baseUrl(DynamicBaseUrlInterceptor.PLACEHOLDER_BASE_URL)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
    }
}
