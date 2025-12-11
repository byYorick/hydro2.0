package com.hydro.app.features.zones

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.auth.SessionManager
import com.hydro.app.core.data.TelemetryRepository
import com.hydro.app.core.data.ZonesRepository
import com.hydro.app.core.domain.CommandRequest
import com.hydro.app.core.domain.CommandResponse
import com.hydro.app.core.domain.TelemetryHistoryPoint
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import com.hydro.app.core.data.ZonesApi
import com.hydro.app.core.domain.usecase.GetZonesUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel для экрана списка зон.
 * 
 * Использует GetZonesUseCase для получения данных.
 */
@HiltViewModel
class ZonesViewModel @Inject constructor(
    private val getZonesUseCase: GetZonesUseCase,
    private val sessionManager: SessionManager
) : ViewModel() {
    private val _greenhouseId = MutableStateFlow<Int?>(null)
    
    /**
     * Состояние списка зон.
     */
    val state: StateFlow<List<Zone>> = _greenhouseId
        .flatMapLatest { ghId ->
            if (ghId != null) {
                getZonesUseCase.getByGreenhouse(ghId)
            } else {
                getZonesUseCase.getAll()
            }
        }
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(com.hydro.app.core.domain.AppConstants.FlowTimeout.STATE_FLOW_TIMEOUT_MS),
            emptyList()
        )

    /**
     * Загружает список зон.
     * 
     * @param greenhouseId Опциональный ID теплицы для фильтрации
     */
    fun load(greenhouseId: Int? = null) {
        _greenhouseId.value = greenhouseId
        viewModelScope.launch {
            sessionManager.updateActivity()
            getZonesUseCase.refresh(greenhouseId)
        }
    }
}

@HiltViewModel
class ZoneDetailsViewModel @Inject constructor(
    private val zonesRepository: ZonesRepository,
    private val telemetryRepository: TelemetryRepository,
    private val zonesApi: ZonesApi,
    private val sessionManager: SessionManager
) : ViewModel() {
    private val _zoneId = MutableStateFlow<Int?>(null)
    private val _telemetryLast = MutableStateFlow<TelemetryLast?>(null)
    private val _telemetryHistory = MutableStateFlow<Map<String, List<TelemetryHistoryPoint>>>(emptyMap())
    private val _zone = MutableStateFlow<Zone?>(null)
    private val _commandState = MutableStateFlow<CommandState>(CommandState.Idle)

    val zone: StateFlow<Zone?> = _zone
    val telemetryLast: StateFlow<TelemetryLast?> = _telemetryLast
    val telemetryHistory: StateFlow<Map<String, List<TelemetryHistoryPoint>>> = _telemetryHistory
    val commandState: StateFlow<CommandState> = _commandState

    sealed interface CommandState {
        data object Idle : CommandState
        data object Loading : CommandState
        data class Success(val response: CommandResponse) : CommandState
        data class Error(val message: String) : CommandState
    }

    fun load(zoneId: Int) {
        _zoneId.value = zoneId
        viewModelScope.launch {
            sessionManager.updateActivity()
            _zone.value = zonesRepository.getById(zoneId)
            loadTelemetryLast(zoneId)
        }
    }

    fun loadTelemetryLast(zoneId: Int) {
        viewModelScope.launch {
            sessionManager.updateActivity()
            _telemetryLast.value = telemetryRepository.getLast(zoneId)
        }
    }

    fun loadHistory(zoneId: Int, metric: String, from: String? = null, to: String? = null) {
        viewModelScope.launch {
            sessionManager.updateActivity()
            telemetryRepository.refreshHistory(zoneId, metric, from, to)
            // Get first value from Flow
            val history = telemetryRepository.getHistory(zoneId, metric).first()
            _telemetryHistory.value = _telemetryHistory.value + (metric to history)
        }
    }

    fun sendCommand(zoneId: Int, command: CommandRequest) {
        _commandState.value = CommandState.Loading
        viewModelScope.launch {
            try {
                sessionManager.updateActivity()
                val response = zonesApi.sendCommand(zoneId, command)
                if (response.status == "ok" && response.data != null) {
                    _commandState.value = CommandState.Success(response.data)
                } else {
                    _commandState.value = CommandState.Error(response.message ?: "Command failed")
                }
            } catch (e: Exception) {
                _commandState.value = CommandState.Error(e.message ?: "Command failed")
            }
        }
    }
}
