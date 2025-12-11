package com.hydro.app.features.greenhouses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.auth.SessionManager
import com.hydro.app.core.domain.AppConstants
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.domain.usecase.GetGreenhousesUseCase
import com.hydro.app.core.realtime.RealtimeService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * ViewModel для экрана списка теплиц.
 * 
 * Использует Use Cases для получения данных, следуя принципам Clean Architecture.
 */
@HiltViewModel
class GreenhousesViewModel @Inject constructor(
    private val getGreenhousesUseCase: GetGreenhousesUseCase,
    private val realtimeService: RealtimeService,
    private val sessionManager: SessionManager
) : ViewModel() {
    /**
     * Состояние списка теплиц.
     */
    val state: StateFlow<List<Greenhouse>> = getGreenhousesUseCase.invoke()
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(AppConstants.FlowTimeout.STATE_FLOW_TIMEOUT_MS),
            emptyList()
        )

    init {
        load()
        // Start polling for updates
        realtimeService.startPolling(
            viewModelScope,
            intervalMs = AppConstants.Polling.GREENHOUSES_INTERVAL_MS
        ) {
            getGreenhousesUseCase.refresh()
        }
    }

    /**
     * Загружает список теплиц из API.
     */
    fun load() {
        viewModelScope.launch {
            sessionManager.updateActivity()
            getGreenhousesUseCase.refresh()
        }
    }
}
