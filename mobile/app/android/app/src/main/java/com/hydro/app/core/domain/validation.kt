package com.hydro.app.core.domain

/**
 * Валидатор для проверки корректности данных.
 */
object Validator {
    /**
     * Паттерн для валидации email адреса.
     */
    private val EMAIL_PATTERN = android.util.Patterns.EMAIL_ADDRESS

    /**
     * Валидирует email адрес.
     * @param email Email адрес для проверки
     * @return true если email валиден, false в противном случае
     */
    fun isValidEmail(email: String): Boolean {
        return email.isNotBlank() && EMAIL_PATTERN.matcher(email).matches()
    }

    /**
     * Валидирует пароль.
     * @param password Пароль для проверки
     * @param minLength Минимальная длина пароля (по умолчанию 6)
     * @return true если пароль валиден, false в противном случае
     */
    fun isValidPassword(password: String, minLength: Int = 6): Boolean {
        return password.length >= minLength
    }

    /**
     * Валидирует ID (должен быть положительным числом).
     * @param id ID для проверки
     * @return true если ID валиден, false в противном случае
     */
    fun isValidId(id: Int?): Boolean {
        return id != null && id > 0
    }

    /**
     * Валидирует строку (не должна быть пустой).
     * @param value Строка для проверки
     * @return true если строка валидна, false в противном случае
     */
    fun isNotBlank(value: String?): Boolean {
        return !value.isNullOrBlank()
    }
}

