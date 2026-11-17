package com.hydro.app.features.settings

import com.hydro.app.core.config.ServerEndpoint
import com.hydro.app.core.prefs.PreferencesDataSource
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ServerSettingsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val preferences = mockk<PreferencesDataSource>()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        every { preferences.serverEndpointFlow } returns flowOf(ServerEndpoint.emulatorDefault)
    }

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun invalidPortIsPreservedAndNeverWrittenAsAnotherNumber() = runTest(dispatcher) {
        val vm = ServerSettingsViewModel(preferences)
        advanceUntilIdle()
        vm.onPort("8x080")
        vm.save()
        advanceUntilIdle()
        assertEquals("8x080", vm.state.value.port)
        assertTrue(vm.state.value.portError != null)
        coVerify(exactly = 0) { preferences.setServerEndpoint(any()) }
    }

    @Test
    fun pastedUrlIsNotSilentlyChangedIntoAnotherProtocolAndPort() = runTest(dispatcher) {
        val vm = ServerSettingsViewModel(preferences)
        advanceUntilIdle()
        vm.onHost("https://hydro.local:9443/api")
        vm.save()
        advanceUntilIdle()
        assertEquals("https://hydro.local:9443/api", vm.state.value.host)
        assertTrue(vm.state.value.hostError != null)
        coVerify(exactly = 0) { preferences.setServerEndpoint(any()) }
    }

    @Test
    fun failedStorageWriteShowsAnErrorAndAllowsRetry() = runTest(dispatcher) {
        coEvery { preferences.setServerEndpoint(any()) } throws java.io.IOException("fixture")
        val vm = ServerSettingsViewModel(preferences)
        advanceUntilIdle()
        vm.save()
        advanceUntilIdle()
        assertFalse(vm.state.value.saved)
        assertFalse(vm.state.value.saving)
        assertEquals("Не удалось сохранить адрес. Повторите попытку.", vm.state.value.message)
    }

    @Test
    fun repeatedClickDoesNotStartAnotherStorageWrite() = runTest(dispatcher) {
        coEvery { preferences.setServerEndpoint(any()) } coAnswers { delay(100); Unit }
        val vm = ServerSettingsViewModel(preferences)
        advanceUntilIdle()
        vm.save()
        vm.save()
        advanceUntilIdle()
        assertTrue(vm.state.value.saved)
        coVerify(exactly = 1) { preferences.setServerEndpoint(any()) }
    }
}
