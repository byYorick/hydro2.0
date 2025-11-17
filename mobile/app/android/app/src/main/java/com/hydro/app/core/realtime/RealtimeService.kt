package com.hydro.app.core.realtime

import com.hydro.app.BuildConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import javax.inject.Inject
import javax.inject.Singleton

sealed class WSEvent {
	data class Text(val text: String) : WSEvent()
	data class Binary(val bytes: ByteString) : WSEvent()
	data object Open : WSEvent()
	data class Closed(val code: Int, val reason: String) : WSEvent()
	data class Failure(val throwable: Throwable) : WSEvent()
}

@Singleton
class RealtimeService @Inject constructor(
	private val okHttpClient: OkHttpClient
) {
	private val scope = CoroutineScope(Dispatchers.IO)
	private var webSocket: WebSocket? = null
	private var reconnectAttempts = 0

	private val _events = MutableSharedFlow<WSEvent>(
		replay = 0,
		extraBufferCapacity = 64,
		onBufferOverflow = BufferOverflow.DROP_OLDEST
	)
	val events: SharedFlow<WSEvent> = _events

	fun start() {
		connect()
	}

	fun stop() {
		webSocket?.cancel()
		webSocket = null
	}

	private fun connect() {
		val request = Request.Builder()
			.url(BuildConfig.WS_BASE_URL)
			.build()
		webSocket = okHttpClient.newWebSocket(request, object : WebSocketListener() {
			override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
				reconnectAttempts = 0
				scope.launch { _events.emit(WSEvent.Open) }
			}

			override fun onMessage(webSocket: WebSocket, text: String) {
				scope.launch { _events.emit(WSEvent.Text(text)) }
			}

			override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
				scope.launch { _events.emit(WSEvent.Binary(bytes)) }
			}

			override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
				scope.launch { _events.emit(WSEvent.Closed(code, reason)) }
				scheduleReconnect()
			}

			override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
				scope.launch { _events.emit(WSEvent.Failure(t)) }
				scheduleReconnect()
			}
		})
	}

	private fun scheduleReconnect() {
		webSocket = null
		reconnectAttempts++
		val delayMs = (1000L * (1 shl (reconnectAttempts.coerceAtMost(5)))).coerceAtMost(30000L)
		scope.launch {
			delay(delayMs)
			connect()
		}
	}
}


