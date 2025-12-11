package com.hydro.app.core.domain.usecase

import com.hydro.app.core.domain.AppConstants
import com.hydro.app.core.domain.AppError
import com.hydro.app.core.domain.AppResult
import com.hydro.app.core.domain.User
import com.hydro.app.core.domain.Validator
import com.hydro.app.core.domain.toAppError
import com.hydro.app.features.auth.data.AuthRepository
import javax.inject.Inject

/**
 * Use Case для авторизации пользователя.
 * 
 * Инкапсулирует бизнес-логику входа:
 * - Валидация входных данных
 * - Вызов репозитория для авторизации
 * - Обработка ошибок
 */
class LoginUseCase @Inject constructor(
    private val repository: AuthRepository
) {
    /**
     * Выполняет вход пользователя.
     * 
     * @param email Email пользователя
     * @param password Пароль пользователя
     * @return Результат с пользователем или ошибкой
     */
    suspend fun invoke(email: String, password: String): AppResult<User> {
        // Валидация email
        if (!Validator.isValidEmail(email)) {
            return Result.failure(
                AppError.ValidationError(
                    message = "Invalid email format",
                    field = "email"
                )
            )
        }

        // Валидация пароля
        if (!Validator.isValidPassword(password)) {
            return Result.failure(
                AppError.ValidationError(
                    message = "Password must be at least ${AppConstants.Validation.MIN_PASSWORD_LENGTH} characters",
                    field = "password"
                )
            )
        }

        // Выполнение авторизации
        return try {
            repository.login(email, password).fold(
                onSuccess = { user -> Result.success(user) },
                onFailure = { error ->
                    Result.failure(
                        when {
                            error.message?.contains("401", ignoreCase = true) == true ||
                            error.message?.contains("unauthorized", ignoreCase = true) == true ||
                            error.message?.contains("Invalid email or password", ignoreCase = true) == true ->
                                AppError.AuthError("Invalid email or password")
                            error.message?.contains("Cannot connect", ignoreCase = true) == true ||
                            error.message?.contains("Connection timeout", ignoreCase = true) == true ||
                            error.message?.contains("Cannot resolve", ignoreCase = true) == true ||
                            error.message?.contains("Network error", ignoreCase = true) == true ->
                                AppError.NetworkError(error.message ?: "Network error")
                            error.message?.contains("HTTP error", ignoreCase = true) == true ->
                                AppError.ServerError(error.message ?: "Server error")
                            else -> error.toAppError()
                        }
                    )
                }
            )
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }
}

