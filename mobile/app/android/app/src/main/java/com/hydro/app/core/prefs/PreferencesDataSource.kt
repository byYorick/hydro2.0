package com.hydro.app.core.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = PreferencesKeys.DATASTORE_NAME)

/**
 * Источник данных для хранения настроек приложения.
 * 
 * Использует DataStore Preferences для безопасного хранения:
 * - Токенов авторизации
 * - URL сервера
 * - WebSocket URL
 * 
 * Все операции асинхронные и потокобезопасные.
 */
class PreferencesDataSource(private val appContext: Context) {
    private val tokenKey = stringPreferencesKey(PreferencesKeys.KEY_TOKEN)
    private val baseUrlKey = stringPreferencesKey(PreferencesKeys.KEY_BASE_URL)
    private val wsUrlKey = stringPreferencesKey(PreferencesKeys.KEY_WS_URL)
    private val loginTimeKey = longPreferencesKey(PreferencesKeys.KEY_LOGIN_TIME)
    private val lastActivityTimeKey = longPreferencesKey(PreferencesKeys.KEY_LAST_ACTIVITY_TIME)

	val tokenFlow: Flow<String?> = appContext.dataStore.data.map { it[tokenKey] }
	val baseUrlFlow: Flow<String?> = appContext.dataStore.data.map { it[baseUrlKey] }
	val wsUrlFlow: Flow<String?> = appContext.dataStore.data.map { it[wsUrlKey] }
	val loginTimeFlow: Flow<Long?> = appContext.dataStore.data.map { it[loginTimeKey] }
	val lastActivityTimeFlow: Flow<Long?> = appContext.dataStore.data.map { it[lastActivityTimeKey] }

	suspend fun setToken(token: String?) {
		appContext.dataStore.edit { prefs ->
			if (token == null) {
				prefs.remove(tokenKey)
				prefs.remove(loginTimeKey)
				prefs.remove(lastActivityTimeKey)
			} else {
				prefs[tokenKey] = token
				val currentTime = System.currentTimeMillis()
				prefs[loginTimeKey] = currentTime
				prefs[lastActivityTimeKey] = currentTime
			}
		}
	}
	
	/**
	 * Обновляет время последней активности пользователя.
	 */
	suspend fun updateLastActivityTime() {
		appContext.dataStore.edit { prefs ->
			prefs[lastActivityTimeKey] = System.currentTimeMillis()
		}
	}
	
	/**
	 * Получает время входа пользователя.
	 */
	suspend fun getLoginTime(): Long? {
		return appContext.dataStore.data.first()[loginTimeKey]
	}
	
	/**
	 * Получает время последней активности.
	 */
	suspend fun getLastActivityTime(): Long? {
		return appContext.dataStore.data.first()[lastActivityTimeKey]
	}

	suspend fun setBaseUrl(url: String?) {
		appContext.dataStore.edit { prefs ->
			if (url == null) prefs.remove(baseUrlKey) else prefs[baseUrlKey] = url
		}
	}

	suspend fun setWsUrl(url: String?) {
		appContext.dataStore.edit { prefs ->
			if (url == null) prefs.remove(wsUrlKey) else prefs[wsUrlKey] = url
		}
	}
}


