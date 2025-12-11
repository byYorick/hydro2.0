package com.hydro.app.core.realtime

import android.util.Log
import com.hydro.app.core.config.ConfigLoader
import com.hydro.app.core.domain.AppConstants
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
import java.net.URI
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Сервис для работы с realtime данными через WebSocket и polling.
 * 
 * Поддерживает:
 * - WebSocket соединения с автоматическим переподключением
 * - Polling для обновления данных
 * - Exponential backoff при переподключении
 */
@Singleton
class RealtimeService @Inject constructor(
    private val configLoader: ConfigLoader,
    private val okHttpClient: OkHttpClient
) {
    private var webSocket: WebSocket? = null
    private var pollingJob: Job? = null
    private var reconnectJob: Job? = null
    private var reconnectAttempts = 0
    private var currentChannel: String? = null
    private var onMessageCallback: ((String) -> Unit)? = null
    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    
    /**
     * Текущее состояние соединения.
     */
    val connectionState: StateFlow<ConnectionState> = _connectionState

    /**
     * Состояния соединения WebSocket.
     */
    enum class ConnectionState {
        /** Соединение разорвано. */
        Disconnected,
        /** Идет подключение. */
        Connecting,
        /** Соединение установлено. */
        Connected,
        /** Ошибка соединения. */
        Error
    }

    /**
     * Запускает polling для периодического обновления данных.
     * 
     * @param scope CoroutineScope для выполнения polling
     * @param intervalMs Интервал между обновлениями в миллисекундах
     * @param onUpdate Функция для выполнения при каждом обновлении
     */
    fun startPolling(
        scope: CoroutineScope,
        intervalMs: Long = AppConstants.Polling.DEFAULT_INTERVAL_MS,
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

    /**
     * Подключается к WebSocket каналу.
     * 
     * @param channel Имя канала для подключения
     * @param onMessage Callback для обработки входящих сообщений
     * @param scope CoroutineScope для автоматического переподключения
     */
    fun connectWebSocket(
        channel: String,
        onMessage: (String) -> Unit,
        scope: CoroutineScope? = null
    ) {
        stop()
        currentChannel = channel
        onMessageCallback = onMessage
        reconnectAttempts = 0
        
        if (scope != null) {
            reconnectJob = scope.launch(Dispatchers.IO) {
                connectWebSocketInternal(channel, onMessage)
            }
        } else {
            connectWebSocketInternal(channel, onMessage)
        }
    }

    /**
     * Внутренний метод для подключения к WebSocket.
     */
    private fun connectWebSocketInternal(channel: String, onMessage: (String) -> Unit) {
        try {
            val config = configLoader.loadConfig()
            val baseUri = URI(config.apiBaseUrl)
            val wsScheme = when (baseUri.scheme) {
                "http" -> "ws"
                "https" -> "wss"
                else -> "wss"
            }
            val wsUrl = "$wsScheme://${baseUri.host}${if (baseUri.port != -1) ":${baseUri.port}" else ""}${baseUri.path}/ws/$channel"
            
            val request = Request.Builder()
                .url(wsUrl)
                .build()

            _connectionState.value = ConnectionState.Connecting
            webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    reconnectAttempts = 0
                    _connectionState.value = ConnectionState.Connected
                    Log.d("RealtimeService", "WebSocket connected to channel: $channel")
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
                    
                    // Автоматическое переподключение
                    if (reconnectAttempts < AppConstants.WebSocket.MAX_RECONNECT_ATTEMPTS) {
                        scheduleReconnect(channel, onMessage)
                    }
                }
            })
        } catch (e: Exception) {
            Log.e("RealtimeService", "WebSocket connection error", e)
            _connectionState.value = ConnectionState.Error
            
            // Автоматическое переподключение
            if (reconnectAttempts < AppConstants.WebSocket.MAX_RECONNECT_ATTEMPTS) {
                scheduleReconnect(channel, onMessage)
            }
        }
    }

    /**
     * Планирует переподключение с exponential backoff.
     */
    private fun scheduleReconnect(channel: String, onMessage: (String) -> Unit) {
        reconnectAttempts++
        val delay = minOf(
            AppConstants.WebSocket.BASE_RECONNECT_DELAY_MS * (1L shl (reconnectAttempts - 1)),
            AppConstants.WebSocket.MAX_RECONNECT_DELAY_MS
        )
        
        reconnectJob?.cancel()
        reconnectJob = kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
            delay(delay)
            Log.d("RealtimeService", "Reconnecting... Attempt $reconnectAttempts")
            connectWebSocketInternal(channel, onMessage)
        }
    }

    /**
     * Останавливает все соединения (WebSocket и polling).
     */
    fun stop() {
        reconnectJob?.cancel()
        reconnectJob = null
        webSocket?.close(1000, null)
        webSocket = null
        pollingJob?.cancel()
        pollingJob = null
        currentChannel = null
        onMessageCallback = null
        reconnectAttempts = 0
        _connectionState.value = ConnectionState.Disconnected
    }
}
