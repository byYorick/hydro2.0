package com.hydro.app.features.operator

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.config.ServerEndpoint
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.prefs.PreferencesDataSource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

data class OverviewUi(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val greenhouses: List<Greenhouse> = emptyList(),
    val activeAlerts: Int = 0,
    val error: String? = null,
    val serverLabel: String = ServerEndpoint.emulatorDefault.label(),
)

@HiltViewModel
class OverviewViewModel @Inject constructor(
    private val repository: OperatorRepository,
    preferences: PreferencesDataSource,
) : ViewModel() {
    private val _state = MutableStateFlow(OverviewUi())
    val state: StateFlow<OverviewUi> = _state
    private var pollJob: Job? = null

    init {
        viewModelScope.launch {
            preferences.serverEndpointFlow.collect { endpoint ->
                _state.update { it.copy(serverLabel = endpoint.label()) }
            }
        }
    }

    fun start() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(POLL_MS)
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(refreshing = it.greenhouses.isNotEmpty(), loading = it.greenhouses.isEmpty()) }
            val houses = repository.greenhouses()
            val alerts = repository.alerts("ACTIVE")
            _state.update {
                it.copy(
                    loading = false,
                    refreshing = false,
                    greenhouses = houses.getOrElse { _ -> it.greenhouses },
                    activeAlerts = alerts.getOrNull()?.size ?: it.activeAlerts,
                    error = houses.exceptionOrNull()?.message,
                )
            }
        }
    }

    private companion object {
        const val POLL_MS = 10_000L
    }
}

data class ZoneListUi(
    val loading: Boolean = true,
    val title: String = "Зоны",
    val zones: List<Zone> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class ZoneListViewModel @Inject constructor(
    private val repository: OperatorRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(ZoneListUi())
    val state: StateFlow<ZoneListUi> = _state
    private var greenhouseId: Int? = null
    private var pollJob: Job? = null

    fun start(id: Int) {
        greenhouseId = id
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(8_000)
            }
        }
    }

    fun refresh() {
        val id = greenhouseId ?: return
        viewModelScope.launch {
            val result = repository.zones(id)
            _state.update {
                it.copy(
                    loading = false,
                    zones = result.getOrElse { emptyList() },
                    title = result.getOrNull()?.firstOrNull()?.greenhouse?.name ?: "Зоны",
                    error = result.exceptionOrNull()?.message,
                )
            }
        }
    }
}

data class AlertsUi(
    val loading: Boolean = true,
    val alerts: List<Alert> = emptyList(),
    val error: String? = null,
    val pendingId: Int? = null,
    val message: String? = null,
)

@HiltViewModel
class OperatorAlertsViewModel @Inject constructor(
    private val repository: OperatorRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(AlertsUi())
    val state: StateFlow<AlertsUi> = _state
    private var pollJob: Job? = null

    fun start() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(5_000)
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            val result = repository.alerts("ACTIVE")
            _state.update {
                it.copy(
                    loading = false,
                    alerts = result.getOrElse { emptyList() },
                    error = result.exceptionOrNull()?.message,
                )
            }
        }
    }

    fun acknowledge(alertId: Int) {
        viewModelScope.launch {
            _state.update { it.copy(pendingId = alertId, message = null) }
            val result = repository.acknowledge(alertId)
            _state.update {
                it.copy(
                    pendingId = null,
                    message = result.fold(
                        onSuccess = { "Алерт подтверждён" },
                        onFailure = { error -> error.message },
                    ),
                    alerts = if (result.isSuccess) it.alerts.filterNot { alert -> alert.id == alertId } else it.alerts,
                )
            }
        }
    }
}
