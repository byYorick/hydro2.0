package com.hydro.app.features.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.BuildConfig
import com.hydro.app.core.config.CleartextPolicy
import com.hydro.app.core.config.ServerEndpoint
import com.hydro.app.core.prefs.PreferencesDataSource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ServerSettingsUi(
    val host: String = ServerEndpoint.DEFAULT_HOST,
    val port: String = ServerEndpoint.DEFAULT_PORT.toString(),
    val useHttps: Boolean = false,
    val cleartextAllowed: Boolean = true,
    val tokenPersisted: Boolean = true,
    val message: String? = null,
    val saved: Boolean = false,
)

@HiltViewModel
class ServerSettingsViewModel @Inject constructor(
    private val preferences: PreferencesDataSource,
) : ViewModel() {
    private val cleartextAllowed = CleartextPolicy.allows(
        endpoint = ServerEndpoint("10.0.2.2", 8080, useHttps = false),
        debugBuild = BuildConfig.DEBUG,
        allowCleartextFlag = BuildConfig.ALLOW_CLEARTEXT,
    )
    private val _state = MutableStateFlow(
        ServerSettingsUi(
            cleartextAllowed = cleartextAllowed,
            tokenPersisted = true,
            useHttps = !cleartextAllowed,
        ),
    )
    val state: StateFlow<ServerSettingsUi> = _state

    init {
        viewModelScope.launch {
            preferences.serverEndpointFlow.collect { endpoint ->
                _state.update {
                    it.copy(
                        host = endpoint.host,
                        port = endpoint.port.toString(),
                        useHttps = if (cleartextAllowed) endpoint.useHttps else true,
                    )
                }
            }
        }
    }

    fun onHost(value: String) = _state.update { it.copy(host = value, saved = false, message = null) }

    fun onPort(value: String) = _state.update { it.copy(port = value.filter { ch -> ch.isDigit() }.take(5), saved = false, message = null) }

    fun onHttps(value: Boolean) {
        if (!value && !cleartextAllowed) {
            _state.update { it.copy(message = CleartextPolicy.rejectionMessage(), useHttps = true) }
            return
        }
        _state.update { it.copy(useHttps = value, saved = false, message = null) }
    }

    fun save() {
        val current = _state.value
        val parsed = ServerEndpoint.parse(current.host, current.port, current.useHttps)
        val endpoint = parsed.getOrElse { error ->
            _state.update { it.copy(message = error.message, saved = false) }
            return
        }
        if (!CleartextPolicy.allows(endpoint, BuildConfig.DEBUG, BuildConfig.ALLOW_CLEARTEXT)) {
            _state.update { it.copy(message = CleartextPolicy.rejectionMessage(), saved = false) }
            return
        }
        viewModelScope.launch {
            preferences.setServerEndpoint(endpoint)
            _state.update { it.copy(saved = true, message = "Адрес сохранён: ${endpoint.label()}") }
        }
    }
}
