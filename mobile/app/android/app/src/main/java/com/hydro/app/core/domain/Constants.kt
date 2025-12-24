package com.hydro.app.core.domain

/**
 * Константы приложения.
 */
object AppConstants {
    /**
     * Интервалы обновления данных (в миллисекундах).
     */
    object Polling {
        /** Стандартный интервал обновления (5 секунд). */
        const val DEFAULT_INTERVAL_MS = 5_000L
        
        /** Интервал обновления для теплиц (10 секунд). */
        const val GREENHOUSES_INTERVAL_MS = 10_000L
        
        /** Интервал обновления для зон (5 секунд). */
        const val ZONES_INTERVAL_MS = 5_000L
    }

    /**
     * Таймауты для подписок Flow (в миллисекундах).
     */
    object FlowTimeout {
        /** Таймаут для подписок StateFlow (5 секунд). */
        const val STATE_FLOW_TIMEOUT_MS = 5_000L
    }

    /**
     * WebSocket настройки.
     */
    object WebSocket {
        /** Максимальное количество попыток переподключения. */
        const val MAX_RECONNECT_ATTEMPTS = 5
        
        /** Базовая задержка перед переподключением (в миллисекундах). */
        const val BASE_RECONNECT_DELAY_MS = 1_000L
        
        /** Максимальная задержка перед переподключением (в миллисекундах). */
        const val MAX_RECONNECT_DELAY_MS = 30_000L
    }

    /**
     * Валидация.
     */
    object Validation {
        /** Минимальная длина пароля. */
        const val MIN_PASSWORD_LENGTH = 6
    }

    /**
     * Настройки сессии авторизации.
     */
    object Session {
        /** Время неактивности до автоматического выхода (в миллисекундах). */
        const val INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000L // 30 минут
        
        /** Максимальное время жизни сессии с момента входа (в миллисекундах). */
        const val MAX_SESSION_DURATION_MS = 24 * 60 * 60 * 1000L // 24 часа
        
        /** Интервал проверки сессии (в миллисекундах). */
        const val CHECK_INTERVAL_MS = 60 * 1000L // 1 минута
    }
}

