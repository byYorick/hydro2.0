package com.hydro.app.features.provisioning

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ProvisioningViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val repository = mockk<ProvisioningRepository>()
    private val device = ProvisioningViewModel.ProvisioningDevice("ESP32")
    private val config = ProvisioningViewModel.ProvisioningConfig("wifi", "password", nodeName = "node", mqttHost = "192.168.1.10")

    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test fun failedRequestNeverShowsSuccess() = runTest(dispatcher) {
        coEvery { repository.provisionDevice(device, config) } returns Result.failure(IllegalStateException("Setup failed"))
        val model = ProvisioningViewModel(repository)
        model.provisionDevice(device, config)
        advanceUntilIdle()
        assertEquals(ProvisioningViewModel.ProvisioningState.Error("Setup failed"), model.state.value)
    }

    @Test fun successfulRequestShowsSuccess() = runTest(dispatcher) {
        coEvery { repository.provisionDevice(device, config) } returns Result.success(Unit)
        val model = ProvisioningViewModel(repository)
        model.provisionDevice(device, config)
        advanceUntilIdle()
        assertEquals(ProvisioningViewModel.ProvisioningState.Success, model.state.value)
    }
}
