package com.hydro.app.features.alerts

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.domain.Alert
import com.hydro.app.core.domain.GetAlertsUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AlertsViewModel @Inject constructor(
	private val getAlerts: GetAlertsUseCase
) : ViewModel() {
	private val _state = MutableStateFlow<List<Alert>>(emptyList())
	val state: StateFlow<List<Alert>> = _state

	fun load() {
		viewModelScope.launch {
			runCatching { getAlerts() }
				.onSuccess { _state.value = it }
		}
	}
}


