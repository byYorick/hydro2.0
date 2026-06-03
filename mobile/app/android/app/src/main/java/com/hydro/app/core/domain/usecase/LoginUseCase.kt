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
                    val message = error.message?.trim().orEmpty().ifEmpty {
                        "Произошла ошибка при входе."
                    }
                    Result.failure(
                        when {
                            error.message?.contains("401", ignoreCase = true) == true ||
                            error.message?.contains("авториз", ignoreCase = true) == true ->
                                AppError.AuthError(message)
                            error.message?.contains("сеть", ignoreCase = true) == true ||
                            error.message?.contains("подключ", ignoreCase = true) == true ||
                            error.message?.contains("ожидан", ignoreCase = true) == true ->
                                AppError.NetworkError(message, error)
                            else -> AppError.UnknownError(message, error)
                        },
                    )
                }
            )
        } catch (e: Exception) {
            Result.failure(e.toAppError())
        }
    }
}

