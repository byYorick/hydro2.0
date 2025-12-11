package com.hydro.app.core.network

import com.hydro.app.core.prefs.PreferencesDataSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Провайдер токена авторизации.
 * 
 * Предоставляет реактивный доступ к токену через StateFlow.
 * Токен автоматически обновляется при изменении в PreferencesDataSource.
 * 
 * Использует SupervisorJob для создания scope, который будет жить весь жизненный цикл приложения.
 * Это безопасно, так как TokenProvider является Singleton и живет пока живет Application.
 */
@Singleton
class TokenProvider @Inject constructor(
    preferences: PreferencesDataSource
) {
    private val scope = CoroutineScope(SupervisorJob())
    
    /**
     * Текущий токен авторизации.
     * 
     * null если пользователь не авторизован.
     * 
     * Использует SharingStarted.WhileSubscribed для автоматического обновления
     * при изменении токена в PreferencesDataSource.
     */
    val tokenState: StateFlow<String?> =
        preferences.tokenFlow.stateIn(
            scope, 
            SharingStarted.WhileSubscribed(5000L), 
            null
        )
}


