package com.hydro.app.features.operator

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.domain.LevelReading
import com.hydro.app.core.domain.Node
import com.hydro.app.core.domain.NodeChannel
import com.hydro.app.core.domain.NodeTelemetrySample
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ZoneOperatorUi(
    val loading: Boolean = true,
    val zone: Zone? = null,
    val telemetry: TelemetryLast? = null,
    val nodes: List<Node> = emptyList(),
    val level: LevelReading? = null,
    val controlMode: String? = null,
    val stage: String? = null,
    val controlModeNote: String? = null,
    val error: String? = null,
    val busy: Boolean = false,
    val message: String? = null,
)

@HiltViewModel
class ZoneOperatorViewModel @Inject constructor(
    private val repository: OperatorRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(ZoneOperatorUi())
    val state: StateFlow<ZoneOperatorUi> = _state
    private var zoneId: Int? = null
    private var pollJob: Job? = null

    fun attach(id: Int) {
        zoneId = id
    }

    fun start(id: Int) {
        attach(id)
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(8_000)
            }
        }
    }

    fun refresh() {
        val id = zoneId ?: return
        viewModelScope.launch {
            val result = repository.zoneDashboard(id)
            _state.update { current ->
                result.fold(
                    onSuccess = { dashboard ->
                        current.copy(
                            loading = false,
                            zone = dashboard.zone,
                            telemetry = dashboard.telemetry,
                            nodes = dashboard.nodes,
                            level = dashboard.level,
                            controlMode = dashboard.controlMode,
                            stage = dashboard.stage,
                            controlModeNote = dashboard.controlModeNote,
                            error = null,
                        )
                    },
                    onFailure = { error ->
                        current.copy(loading = false, error = error.message)
                    },
                )
            }
        }
    }

    fun irrigate(durationSec: Int) {
        val id = zoneId ?: return
        if (durationSec !in 1..3600) {
            _state.update { it.copy(message = "Длительность полива: 1–3600 секунд") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, message = null) }
            val result = repository.forceIrrigation(id, durationSec)
            _state.update {
                it.copy(busy = false, message = result.fold(onSuccess = { idText -> "Полив: $idText" }, onFailure = { error -> error.message }))
            }
        }
    }

    fun emergencyManual(reason: String) {
        val id = zoneId ?: return
        if (reason.isBlank()) {
            _state.update { it.copy(message = "Для аварийного перевода в ручной режим нужна причина") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, message = null) }
            val result = repository.emergencyManual(id, reason.trim())
            _state.update {
                it.copy(
                    busy = false,
                    controlMode = if (result.isSuccess) "manual" else it.controlMode,
                    message = result.fold(onSuccess = { text -> text }, onFailure = { error -> error.message }),
                )
            }
            if (result.isSuccess) refresh()
        }
    }

    fun clearMessage() {
        _state.update { it.copy(message = null) }
    }
}

data class NodeOperatorUi(
    val loading: Boolean = true,
    val node: Node? = null,
    val samples: List<NodeTelemetrySample> = emptyList(),
    val error: String? = null,
    val busy: Boolean = false,
    val message: String? = null,
) {
    val actuators: List<NodeChannel>
        get() = node?.channels.orEmpty().filter { channel ->
            channel.type.equals("ACTUATOR", ignoreCase = true) && !channel.channel.isNullOrBlank()
        }
}

@HiltViewModel
class NodeOperatorViewModel @Inject constructor(
    private val repository: OperatorRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(NodeOperatorUi())
    val state: StateFlow<NodeOperatorUi> = _state
    private var nodeId: Int? = null
    private var pollJob: Job? = null

    fun start(id: Int) {
        nodeId = id
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(8_000)
            }
        }
    }

    fun refresh() {
        val id = nodeId ?: return
        viewModelScope.launch {
            val result = repository.nodeDashboard(id)
            _state.update { current ->
                result.fold(
                    onSuccess = { dashboard ->
                        current.copy(loading = false, node = dashboard.node, samples = dashboard.samples, error = null)
                    },
                    onFailure = { error -> current.copy(loading = false, error = error.message) },
                )
            }
        }
    }

    fun restart() {
        val id = nodeId ?: return
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            val result = repository.restartNode(id)
            _state.update {
                it.copy(busy = false, message = result.fold(onSuccess = { text -> text }, onFailure = { error -> error.message }))
            }
        }
    }

    fun setRelay(channel: String, enabled: Boolean) {
        val id = nodeId ?: return
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            val result = repository.setRelay(id, channel, enabled)
            _state.update {
                it.copy(busy = false, message = result.fold(onSuccess = { text -> text }, onFailure = { error -> error.message }))
            }
        }
    }
}
