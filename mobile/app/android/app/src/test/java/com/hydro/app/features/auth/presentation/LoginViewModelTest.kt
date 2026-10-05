package com.hydro.app.features.auth.presentation

import app.cash.turbine.test
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.User
import com.hydro.app.core.domain.usecase.LoginUseCase
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
import io.mockk.coEvery
import io.mockk.mockk

/**
 * Unit тесты для LoginViewModel.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class LoginViewModelTest {
    private lateinit var loginUseCase: LoginUseCase
    private lateinit var viewModel: LoginViewModel
    private val mainDispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(mainDispatcher)
        loginUseCase = mockk()
        viewModel = LoginViewModel(loginUseCase, mockk(relaxed = true))
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `initial state is Idle`() = runTest(mainDispatcher) {
        // Then
        assertEquals(LoginState.Idle, viewModel.state.value)
    }

    @Test
    fun `login with valid credentials updates state to Success`() = runTest(mainDispatcher) {
        // Given
        val email = "test@example.com"
        val password = "password123"
        val user = User(id = 1, name = "Test User", email = email)
        
        coEvery { loginUseCase.invoke(email, password) } returns kotlin.Result.success(user)

        // When
        viewModel.state.test {
            assertEquals(LoginState.Idle, awaitItem())
            viewModel.login(email, password)
            assertEquals(LoginState.Loading, awaitItem())
            advanceUntilIdle()

            // Then
            val successState = awaitItem() as LoginState.Success
            assertEquals(user, successState.user)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `login with invalid credentials updates state to Error`() = runTest(mainDispatcher) {
        // Given
        val email = "test@example.com"
        val password = "wrong"
        val error = AppError.AuthError("Invalid credentials")
        
        coEvery { loginUseCase.invoke(email, password) } returns kotlin.Result.failure(error)

        // When
        viewModel.state.test {
            assertEquals(LoginState.Idle, awaitItem())
            viewModel.login(email, password)
            assertEquals(LoginState.Loading, awaitItem())
            advanceUntilIdle()

            // Then
            val errorState = awaitItem() as LoginState.Error
            assertEquals("Invalid credentials", errorState.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}
