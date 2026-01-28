package com.hydro.app.core.domain.usecase

import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.User
import com.hydro.app.features.auth.data.AuthRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Unit тесты для LoginUseCase.
 */
class LoginUseCaseTest {
    private lateinit var authRepository: AuthRepository
    private lateinit var loginUseCase: LoginUseCase

    @Before
    fun setup() {
        authRepository = mockk()
        loginUseCase = LoginUseCase(authRepository)
    }

    @Test
    fun `login with valid credentials returns success`() = runTest {
        // Given
        val email = "test@example.com"
        val password = "password123"
        val user = User(id = 1, name = "Test User", email = email)
        
        coEvery { authRepository.login(email, password) } returns Result.success(user)

        // When
        val result = loginUseCase.invoke(email, password)

        // Then
        assertTrue(result.isSuccess)
        assertEquals(user, result.getOrNull())
        coVerify(exactly = 1) { authRepository.login(email, password) }
    }

    @Test
    fun `login with invalid email returns validation error`() = runTest {
        // Given
        val email = "invalid-email"
        val password = "password123"

        // When
        val result = loginUseCase.invoke(email, password)

        // Then
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is AppError.ValidationError)
        coVerify(exactly = 0) { authRepository.login(any(), any()) }
    }

    @Test
    fun `login with short password returns validation error`() = runTest {
        // Given
        val email = "test@example.com"
        val password = "12345" // меньше 6 символов

        // When
        val result = loginUseCase.invoke(email, password)

        // Then
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is AppError.ValidationError)
        coVerify(exactly = 0) { authRepository.login(any(), any()) }
    }

    @Test
    fun `login with auth error returns AuthError`() = runTest {
        // Given
        val email = "test@example.com"
        val password = "password123"
        val error = Exception("401 Unauthorized")
        
        coEvery { authRepository.login(email, password) } returns Result.failure(error)

        // When
        val result = loginUseCase.invoke(email, password)

        // Then
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is AppError.AuthError)
    }
}

