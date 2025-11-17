package com.hydro.app.features.greenhouses

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.domain.GetGreenhousesUseCase
import com.hydro.app.core.domain.Greenhouse
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class GreenhousesViewModel @Inject constructor(
	private val getGreenhouses: GetGreenhousesUseCase
) : ViewModel() {
	private val _state = MutableStateFlow<List<Greenhouse>>(emptyList())
	val state: StateFlow<List<Greenhouse>> = _state

	fun load() {
		viewModelScope.launch {
			runCatching { getGreenhouses() }
				.onSuccess { _state.value = it }
		}
	}
}


