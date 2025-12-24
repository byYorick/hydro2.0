package com.hydro.app.features.auth.presentation

import app.cash.turbine.test
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.User
import com.hydro.app.core.domain.usecase.LoginUseCase
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import io.mockk.coEvery
import io.mockk.mockk

/**
 * Unit тесты для LoginViewModel.
 */
class LoginViewModelTest {
    private lateinit var loginUseCase: LoginUseCase
    private lateinit var viewModel: LoginViewModel

    @Before
    fun setup() {
        loginUseCase = mockk()
        viewModel = LoginViewModel(loginUseCase)
    }

    @Test
    fun `initial state is Idle`() = runTest {
        // Then
        assertEquals(LoginState.Idle, viewModel.state.value)
    }

    @Test
    fun `login with valid credentials updates state to Success`() = runTest {
        // Given
        val email = "test@example.com"
        val password = "password123"
        val user = User(id = 1, name = "Test User", email = email)
        
        coEvery { loginUseCase.invoke(email, password) } returns kotlin.Result.success(user)

        // When
        viewModel.state.test {
            viewModel.login(email, password)
            advanceUntilIdle()

            // Then
            assertEquals(LoginState.Loading, awaitItem())
            val successState = awaitItem() as LoginState.Success
            assertEquals(user, successState.user)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `login with invalid credentials updates state to Error`() = runTest {
        // Given
        val email = "test@example.com"
        val password = "wrong"
        val error = AppError.AuthError("Invalid credentials")
        
        coEvery { loginUseCase.invoke(email, password) } returns kotlin.Result.failure(error)

        // When
        viewModel.state.test {
            viewModel.login(email, password)
            advanceUntilIdle()

            // Then
            assertEquals(LoginState.Loading, awaitItem())
            val errorState = awaitItem() as LoginState.Error
            assertEquals("Authentication failed", errorState.message)
            cancelAndIgnoreRemainingEvents()
        }
    }
}

