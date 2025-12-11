package com.hydro.app.core.realtime

import android.util.Log
import com.hydro.app.core.config.ConfigLoader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RealtimeService @Inject constructor(
    private val configLoader: ConfigLoader,
    private val okHttpClient: OkHttpClient
) {
    private var webSocket: WebSocket? = null
    private var pollingJob: Job? = null
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    enum class ConnectionState {
        Disconnected,
        Connecting,
        Connected,
        Error
    }

    fun startPolling(
        scope: CoroutineScope,
        intervalMs: Long = 5000,
        onUpdate: suspend () -> Unit
    ) {
        stop()
        _connectionState.value = ConnectionState.Connecting
        pollingJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                try {
                    onUpdate()
                    _connectionState.value = ConnectionState.Connected
                } catch (e: Exception) {
                    Log.e("RealtimeService", "Polling error", e)
                    _connectionState.value = ConnectionState.Error
                }
                delay(intervalMs)
            }
        }
    }

    fun connectWebSocket(
        channel: String,
        onMessage: (String) -> Unit
    ) {
        stop()
        try {
            val config = configLoader.loadConfig()
            val wsUrl = config.apiBaseUrl.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
            val request = Request.Builder()
                .url("$wsUrl/$channel")
                .build()

            _connectionState.value = ConnectionState.Connecting
            webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    _connectionState.value = ConnectionState.Connected
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    onMessage(text)
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    onMessage(bytes.utf8())
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d("RealtimeService", "WebSocket closing: code=$code, reason=$reason")
                    webSocket.close(1000, null)
                    _connectionState.value = ConnectionState.Disconnected
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e("RealtimeService", "WebSocket connection failed", t)
                    webSocket.close(1000, null)
                    _connectionState.value = ConnectionState.Error
                }
            })
        } catch (e: Exception) {
            Log.e("RealtimeService", "WebSocket connection error", e)
            _connectionState.value = ConnectionState.Error
        }
    }

    fun stop() {
        webSocket?.close(1000, null)
        webSocket = null
        pollingJob?.cancel()
        pollingJob = null
        _connectionState.value = ConnectionState.Disconnected
    }
}
