package com.hydro.app.core.config

import com.hydro.app.core.prefs.PreferencesDataSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Синхронный снимок адреса сервера для OkHttp-интерсептора.
 */
@Singleton
class ServerEndpointStore @Inject constructor(
    private val preferences: PreferencesDataSource,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val state = MutableStateFlow(ServerEndpoint.emulatorDefault)

    init {
        runBlocking(Dispatchers.IO) {
            state.value = preferences.serverEndpointFlow.first()
        }
        scope.launch {
            preferences.serverEndpointFlow.collect { state.value = it }
        }
    }

    fun current(): ServerEndpoint = state.value
}
