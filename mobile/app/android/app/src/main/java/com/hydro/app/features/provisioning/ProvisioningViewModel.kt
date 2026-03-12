package com.hydro.app.features.provisioning

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProvisioningViewModel @Inject constructor(
	private val repo: ProvisioningRepository
) : ViewModel() {
	private val _state = MutableStateFlow<String?>(null)
	val state: StateFlow<String?> = _state

	fun sendDemo() {
		viewModelScope.launch {
			val res = repo.sendProvision(
				wifiSsid = "MyWiFi",
				wifiPassword = "password",
				backendUrl = "https://your-backend.example",
				ghUid = "gh-main",
				zoneUid = "zone-a"
			)
			_state.value = res.fold(onSuccess = { "OK" }, onFailure = { it.message ?: "Error" })
		}
	}
}


