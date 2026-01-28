package com.hydro.app.core.domain

/**
 * Базовый класс для всех ошибок приложения.
 * Используется для унифицированной обработки ошибок во всех слоях приложения.
 * 
 * Наследуется от Throwable для совместимости с Result.failure().
 */
sealed class AppError(
    override val message: String,
    override val cause: Throwable? = null
) : Throwable(message, cause) {

    /**
     * Ошибка сети (нет интернета, таймаут, и т.д.)
     */
    data class NetworkError(
        override val message: String,
        override val cause: Throwable? = null
    ) : AppError(message, cause)

    /**
     * Ошибка сервера (5xx)
     */
    data class ServerError(
        override val message: String,
        val code: Int? = null
    ) : AppError(message)

    /**
     * Ошибка авторизации (401, 403)
     */
    data class AuthError(
        override val message: String = "Authentication failed"
    ) : AppError(message)

    /**
     * Ошибка валидации данных
     */
    data class ValidationError(
        override val message: String,
        val field: String? = null
    ) : AppError(message)

    /**
     * Ошибка базы данных
     */
    data class DatabaseError(
        override val message: String,
        override val cause: Throwable? = null
    ) : AppError(message, cause)

    /**
     * Неизвестная ошибка
     */
    data class UnknownError(
        override val message: String = "An unknown error occurred",
        override val cause: Throwable? = null
    ) : AppError(message, cause)
}

/**
 * Результат операции, который может быть успешным или содержать ошибку.
 */
typealias AppResult<T> = Result<T>

/**
 * Расширение для преобразования исключений в AppError.
 */
fun Throwable.toAppError(): AppError {
    return when (this) {
        is java.net.UnknownHostException,
        is java.net.SocketTimeoutException,
        is java.io.IOException -> AppError.NetworkError(
            message = this.message ?: "Network error",
            cause = this
        )
        else -> AppError.UnknownError(
            message = this.message ?: "Unknown error",
            cause = this
        )
    }
}

