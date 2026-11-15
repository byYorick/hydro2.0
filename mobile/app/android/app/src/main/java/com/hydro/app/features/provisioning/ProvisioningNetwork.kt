package com.hydro.app.features.provisioning

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import dagger.hilt.android.qualifiers.ApplicationContext
import okhttp3.OkHttpClient
import okhttp3.Dns
import java.net.InetAddress
import javax.inject.Inject

/** Bind setup traffic to the local WiFi route even when cellular is the default. */
class ProvisioningNetwork @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun bind(client: OkHttpClient): OkHttpClient {
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val address = InetAddress.getByName("192.168.4.1")
        val candidates = manager.allNetworks.filter { network ->
            val capabilities = manager.getNetworkCapabilities(network)
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true &&
                !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN) &&
                manager.getLinkProperties(network)?.routes.orEmpty().any { route ->
                    !route.hasGateway() && route.destination.prefixLength > 0 && route.matches(address)
                }
        }
        val network = candidates.singleOrNull()
            ?: error("Подключитесь к Wi-Fi сети ESP32 перед настройкой")
        return client.newBuilder()
            .socketFactory(network.socketFactory)
            .dns(object : Dns {
                override fun lookup(hostname: String): List<InetAddress> = network.getAllByName(hostname).toList()
            })
            .build()
    }
}
