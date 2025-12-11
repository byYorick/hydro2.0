package com.hydro.app.core.auth

import com.hydro.app.core.domain.AppConstants
import com.hydro.app.core.prefs.PreferencesDataSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Менеджер сессии пользователя.
 * 
 * Отслеживает время неактивности и автоматически завершает сессию при:
 * - Превышении времени неактивности (по умолчанию 30 минут)
 * - Превышении максимального времени жизни сессии (по умолчанию 24 часа)
 * 
 * Автоматически обновляет время последней активности при каждом действии пользователя.
 */
@Singleton
class SessionManager @Inject constructor(
    private val prefs: PreferencesDataSource
) {
    private var checkJob: Job? = null
    private val _isSessionValid = MutableStateFlow<Boolean?>(null)
    
    /**
     * Состояние валидности сессии.
     * - null: сессия не проверена или пользователь не авторизован
     * - true: сессия валидна
     * - false: сессия истекла
     */
    val isSessionValid: StateFlow<Boolean?> = _isSessionValid

    /**
     * Запускает мониторинг сессии.
     * 
     * @param scope CoroutineScope для выполнения проверок
     * @param onSessionExpired Callback вызываемый при истечении сессии
     */
    fun startSessionMonitoring(
        scope: CoroutineScope,
        onSessionExpired: suspend () -> Unit
    ) {
        stopSessionMonitoring()
        
        checkJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                val isValid = checkSession()
                _isSessionValid.value = isValid
                
                if (isValid == false) {
                    // Сессия истекла - выполняем logout
                    onSessionExpired()
                    stopSessionMonitoring()
                    break
                }
                
                delay(AppConstants.Session.CHECK_INTERVAL_MS)
            }
        }
    }

    /**
     * Останавливает мониторинг сессии.
     */
    fun stopSessionMonitoring() {
        checkJob?.cancel()
        checkJob = null
        _isSessionValid.value = null
    }

    /**
     * Обновляет время последней активности пользователя.
     * 
     * Должно вызываться при каждом действии пользователя (нажатие кнопки, навигация, и т.д.).
     */
    suspend fun updateActivity() {
        prefs.updateLastActivityTime()
    }

    /**
     * Проверяет валидность текущей сессии.
     * 
     * @return true если сессия валидна, false если истекла, null если пользователь не авторизован
     */
    suspend fun checkSession(): Boolean? {
        val token = prefs.tokenFlow.first()
        if (token.isNullOrBlank()) {
            return null
        }

        val loginTime = prefs.getLoginTime()
        val lastActivityTime = prefs.getLastActivityTime()
        
        if (loginTime == null || lastActivityTime == null) {
            // Нет данных о времени - считаем сессию невалидной
            return false
        }

        val currentTime = System.currentTimeMillis()
        
        // Проверка максимального времени жизни сессии
        val sessionAge = currentTime - loginTime
        if (sessionAge > AppConstants.Session.MAX_SESSION_DURATION_MS) {
            return false
        }

        // Проверка времени неактивности
        val inactivityTime = currentTime - lastActivityTime
        if (inactivityTime > AppConstants.Session.INACTIVITY_TIMEOUT_MS) {
            return false
        }

        return true
    }

    /**
     * Принудительно завершает сессию.
     */
    suspend fun invalidateSession() {
        prefs.setToken(null)
        stopSessionMonitoring()
        _isSessionValid.value = false
    }
}

