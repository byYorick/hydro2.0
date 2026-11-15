package com.hydro.app.features.provisioning

import android.content.Context
import android.net.ConnectivityManager
import android.net.IpPrefix
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.net.RouteInfo
import io.mockk.every
import io.mockk.mockk
import okhttp3.OkHttpClient
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Test
import javax.net.SocketFactory

class ProvisioningNetworkTest {
    private val context = mockk<Context>()
    private val manager = mockk<ConnectivityManager>()

    init {
        every { context.getSystemService(Context.CONNECTIVITY_SERVICE) } returns manager
    }

    @Test fun bindsLocalWifiInsteadOfDefaultCellular() {
        val cellular = mockk<Network>()
        val wifi = mockk<Network>()
        val cellCaps = mockk<NetworkCapabilities>()
        val wifiCaps = mockk<NetworkCapabilities>()
        val links = mockk<LinkProperties>()
        val route = mockk<RouteInfo>()
        val prefix = mockk<IpPrefix>()
        val sockets = SocketFactory.getDefault()
        every { manager.allNetworks } returns arrayOf(cellular, wifi)
        every { manager.getNetworkCapabilities(cellular) } returns cellCaps
        every { cellCaps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) } returns false
        every { manager.getNetworkCapabilities(wifi) } returns wifiCaps
        every { wifiCaps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) } returns true
        every { wifiCaps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) } returns false
        every { manager.getLinkProperties(wifi) } returns links
        every { links.routes } returns listOf(route)
        every { route.hasGateway() } returns false
        every { route.destination } returns prefix
        every { prefix.prefixLength } returns 24
        every { route.matches(any()) } returns true
        every { wifi.socketFactory } returns sockets
        val client = ProvisioningNetwork(context).bind(OkHttpClient())
        assertSame(sockets, client.socketFactory)
    }

    @Test fun refusesVpnRouteEvenIfItAdvertisesWifiTransport() {
        val vpn = mockk<Network>()
        val capabilities = mockk<NetworkCapabilities>()
        every { manager.allNetworks } returns arrayOf(vpn)
        every { manager.getNetworkCapabilities(vpn) } returns capabilities
        every { capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) } returns true
        every { capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN) } returns true
        assertThrows(IllegalStateException::class.java) {
            ProvisioningNetwork(context).bind(OkHttpClient())
        }
    }

    @Test fun refusesCellularFallbackWhenSetupWifiIsAbsent() {
        val cellular = mockk<Network>()
        val capabilities = mockk<NetworkCapabilities>()
        every { manager.allNetworks } returns arrayOf(cellular)
        every { manager.getNetworkCapabilities(cellular) } returns capabilities
        every { capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) } returns false
        assertThrows(IllegalStateException::class.java) {
            ProvisioningNetwork(context).bind(OkHttpClient())
        }
    }
}
