package com.hydro.app.features.operator

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import io.mockk.coVerify
import io.mockk.mockk
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ZoneOperatorViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val repository = mockk<OperatorRepository>()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun emergencyManualRequiresReason() = runTest(dispatcher) {
        val viewModel = ZoneOperatorViewModel(repository)
        viewModel.attach(7)
        viewModel.emergencyManual("   ")
        advanceUntilIdle()
        coVerify(exactly = 0) { repository.emergencyManual(any(), any()) }
        assertEquals("Для аварийного перевода в ручной режим нужна причина", viewModel.state.value.message)
    }

    @Test
    fun irrigationRejectsDurationOutsideApiBounds() = runTest(dispatcher) {
        val viewModel = ZoneOperatorViewModel(repository)
        viewModel.attach(3)
        viewModel.irrigate(0)
        advanceUntilIdle()
        coVerify(exactly = 0) { repository.forceIrrigation(any(), any()) }
        assertEquals("Длительность полива: 1–3600 секунд", viewModel.state.value.message)
    }
}
