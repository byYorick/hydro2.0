package com.hydro.app.features.greenhouses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.data.GreenhousesRepository
import com.hydro.app.core.domain.Greenhouse
import com.hydro.app.core.realtime.RealtimeService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class GreenhousesViewModel @Inject constructor(
    private val repository: GreenhousesRepository,
    private val realtimeService: RealtimeService
) : ViewModel() {
    val state: StateFlow<List<Greenhouse>> = repository.getAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    init {
        load()
        // Start polling for updates
        realtimeService.startPolling(viewModelScope, intervalMs = 10000) {
            repository.refresh()
        }
    }

    fun load() {
        viewModelScope.launch {
            repository.refresh()
        }
    }
}
