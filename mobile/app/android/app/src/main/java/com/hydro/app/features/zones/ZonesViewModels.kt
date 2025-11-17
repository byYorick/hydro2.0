package com.hydro.app.features.zones

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.domain.GetZoneDetailsUseCase
import com.hydro.app.core.domain.GetZonesUseCase
import com.hydro.app.core.domain.TelemetryLast
import com.hydro.app.core.domain.Zone
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ZonesViewModel @Inject constructor(
	private val getZones: GetZonesUseCase
) : ViewModel() {
	private val _state = MutableStateFlow<List<Zone>>(emptyList())
	val state: StateFlow<List<Zone>> = _state
	fun load(greenhouseId: String) {
		viewModelScope.launch {
			runCatching { getZones(greenhouseId) }
				.onSuccess { _state.value = it }
		}
	}
}

@HiltViewModel
class ZoneDetailsViewModel @Inject constructor(
	private val getZoneDetails: GetZoneDetailsUseCase
) : ViewModel() {
	private val _state = MutableStateFlow<TelemetryLast?>(null)
	val state: StateFlow<TelemetryLast?> = _state
	fun load(zoneId: String) {
		viewModelScope.launch {
			runCatching { getZoneDetails(zoneId) }
				.onSuccess { _state.value = it }
		}
	}
}


