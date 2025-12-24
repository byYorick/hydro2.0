package com.hydro.app.features.provisioning

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hydro.app.core.config.ConfigLoader
import com.hydro.app.features.provisioning.ProvisioningRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ProvisioningViewModel @Inject constructor(
    private val repository: ProvisioningRepository,
    private val configLoader: ConfigLoader
) : ViewModel() {
    private val _state = MutableStateFlow<ProvisioningState>(ProvisioningState.Idle)
    val state: StateFlow<ProvisioningState> = _state

    sealed interface ProvisioningState {
        data object Idle : ProvisioningState
        data object Scanning : ProvisioningState
        data class FoundDevices(val devices: List<ProvisioningDevice>) : ProvisioningState
        data object Configuring : ProvisioningState
        data object Success : ProvisioningState
        data class Error(val message: String) : ProvisioningState
    }

    data class ProvisioningDevice(
        val ssid: String,
        val ipAddress: String? = null
    )

    data class ProvisioningConfig(
        val wifiSsid: String,
        val wifiPassword: String,
        val greenhouseUid: String? = null,
        val zoneUid: String? = null,
        val nodeName: String
    )

    fun scanDevices() {
        _state.value = ProvisioningState.Scanning
        viewModelScope.launch {
            try {
                val devices = repository.scanForDevices()
                _state.value = ProvisioningState.FoundDevices(devices)
            } catch (e: Exception) {
                _state.value = ProvisioningState.Error(e.message ?: "Scan failed")
            }
        }
    }

    fun provisionDevice(device: ProvisioningDevice, config: ProvisioningConfig) {
        _state.value = ProvisioningState.Configuring
        viewModelScope.launch {
            try {
                val backendUrl = configLoader.loadConfig().apiBaseUrl
                repository.provisionDevice(device, config, backendUrl)
                _state.value = ProvisioningState.Success
            } catch (e: Exception) {
                _state.value = ProvisioningState.Error(e.message ?: "Provisioning failed")
            }
        }
    }
}
