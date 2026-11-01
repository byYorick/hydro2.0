package com.hydro.app.core.config

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerEndpointTest {
    @Test
    fun emulatorDefaultPointsAtHostLoopback() {
        val endpoint = ServerEndpoint.emulatorDefault
        assertEquals("http://10.0.2.2:8080/", endpoint.baseUrl())
    }

    @Test
    fun parseStripsSchemeAndPath() {
        val endpoint = ServerEndpoint.parse("http://192.168.1.20/api", "8080", false).getOrThrow()
        assertEquals("192.168.1.20", endpoint.host)
        assertEquals(8080, endpoint.port)
        assertEquals("http://192.168.1.20:8080/", endpoint.baseUrl())
    }

    @Test
    fun parseRejectsBadPort() {
        assertTrue(ServerEndpoint.parse("10.0.2.2", "0", false).isFailure)
        assertTrue(ServerEndpoint.parse(" ", "8080", false).isFailure)
    }
}

class CleartextPolicyTest {
    @Test
    fun httpsAlwaysAllowed() {
        val endpoint = ServerEndpoint("greenhouse.local", 443, useHttps = true)
        assertTrue(CleartextPolicy.allows(endpoint, debugBuild = false, allowCleartextFlag = false))
    }

    @Test
    fun httpOnlyInDebugOrExplicitFlag() {
        val endpoint = ServerEndpoint("10.0.2.2", 8080, useHttps = false)
        assertTrue(CleartextPolicy.allows(endpoint, debugBuild = true, allowCleartextFlag = false))
        assertFalse(CleartextPolicy.allows(endpoint, debugBuild = false, allowCleartextFlag = false))
        assertTrue(CleartextPolicy.allows(endpoint, debugBuild = false, allowCleartextFlag = true))
    }
}
