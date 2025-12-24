package com.hydro.app.features.alerts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.data.AlertsRepository
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.realtime.RealtimeService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AlertsViewModel @Inject constructor(
    private val repository: AlertsRepository,
    private val realtimeService: RealtimeService
) : ViewModel() {
    private val _filterStatus = MutableStateFlow<String?>(null)
    private val _filterZoneId = MutableStateFlow<Int?>(null)
    private val _acknowledgeState = MutableStateFlow<AcknowledgeState>(AcknowledgeState.Idle)

    val state: StateFlow<List<Alert>> = _filterStatus.value?.let { status ->
        repository.getByStatus(status)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    } ?: _filterZoneId.value?.let { zoneId ->
        repository.getByZone(zoneId)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    } ?: repository.getAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val acknowledgeState: StateFlow<AcknowledgeState> = _acknowledgeState

    sealed interface AcknowledgeState {
        data object Idle : AcknowledgeState
        data object Loading : AcknowledgeState
        data object Success : AcknowledgeState
        data class Error(val message: String) : AcknowledgeState
    }

    init {
        load()
        // Start polling for updates
        realtimeService.startPolling(viewModelScope, intervalMs = 5000) {
            repository.refresh(_filterZoneId.value, _filterStatus.value)
        }
    }

    fun load(zoneId: Int? = null, status: String? = null) {
        _filterZoneId.value = zoneId
        _filterStatus.value = status
        viewModelScope.launch {
            repository.refresh(zoneId, status)
        }
    }

    fun acknowledge(alertId: Int) {
        _acknowledgeState.value = AcknowledgeState.Loading
        viewModelScope.launch {
            val result = repository.acknowledge(alertId)
            _acknowledgeState.value = result.fold(
                onSuccess = { AcknowledgeState.Success },
                onFailure = { AcknowledgeState.Error(it.message ?: "Failed to acknowledge") }
            )
            // Reset after a delay
            kotlinx.coroutines.delay(2000)
            _acknowledgeState.value = AcknowledgeState.Idle
        }
    }
}
