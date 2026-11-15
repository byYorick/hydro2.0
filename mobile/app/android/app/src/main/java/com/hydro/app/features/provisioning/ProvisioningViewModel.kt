package com.hydro.app.features.provisioning

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import javax.inject.Inject

@HiltViewModel
class ProvisioningViewModel @Inject constructor(
    private val repository: ProvisioningRepository
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
        val nodeName: String,
        val mqttHost: String,
        val mqttPort: Int = 1883
    )

    fun configureConnectedDevice() {
        _state.value = ProvisioningState.FoundDevices(listOf(ProvisioningDevice("Подключённый ESP32", "192.168.4.1")))
    }

    fun scanDevices() {
        _state.value = ProvisioningState.Scanning
        viewModelScope.launch {
            try {
                val devices = repository.scanForDevices()
                _state.value = ProvisioningState.FoundDevices(devices)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = ProvisioningState.Error(e.message ?: "Scan failed")
            }
        }
    }

    fun provisionDevice(device: ProvisioningDevice, config: ProvisioningConfig) {
        _state.value = ProvisioningState.Configuring
        viewModelScope.launch {
            try {
                repository.provisionDevice(device, config).getOrThrow()
                _state.value = ProvisioningState.Success
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = ProvisioningState.Error(e.message ?: "Provisioning failed")
            }
        }
    }
}
